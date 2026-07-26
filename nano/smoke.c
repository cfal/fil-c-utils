/* Functional gate for the Fil-C nano build.
 *
 * nano is purely interactive, so the only way to actually run it -- as the
 * project's "run every exported command before shipping it" rule requires --
 * is to drive it through a pseudo-terminal. This harness allocates its own pty
 * (so it works inside a container with no controlling TTY), launches nano on a
 * scratch file, types a line, saves with ^O, and exits with ^X.
 *
 * It runs nano with TERMINFO and TERMINFO_DIRS pointed at a path that does not
 * exist, so ncurses cannot read any terminfo database from disk. The only way
 * nano can then drive the terminal is the fallback entries compiled into the
 * library, which is exactly the situation in the scratch image. If the file
 * comes back holding the typed text, terminal setup, input, editing and saving
 * all worked with no terminfo on disk.
 *
 * Exit status is 0 only when nano exited cleanly and the file holds precisely
 * the expected bytes; any other outcome is a nonzero failure.
 *
 * usage: smoke <path-to-nano> <scratch-file>
 */
#define _XOPEN_SOURCE 700
#include <pty.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <sys/wait.h>
#include <sys/select.h>

static const char EXPECTED[] = "Hello Fil-C nano\n";

static void nap(int msec)
{
	struct timespec t = { msec / 1000, (long)(msec % 1000) * 1000000L };
	nanosleep(&t, NULL);
}

/* Read whatever nano has drawn for up to msec, echoing it to stderr so a
   failed run leaves nano's last screen in the build log. */
static void drain(int mfd, int msec)
{
	char buf[8192];
	for (int waited = 0; waited < msec; waited += 50) {
		fd_set r;
		struct timeval tv = { 0, 50000 };
		FD_ZERO(&r);
		FD_SET(mfd, &r);
		if (select(mfd + 1, &r, NULL, NULL, &tv) <= 0)
			return;
		int n = read(mfd, buf, sizeof buf);
		if (n <= 0)
			return;
		fwrite(buf, 1, (size_t)n, stderr);
	}
}

static int send(int fd, const char *s)
{
	size_t len = strlen(s);
	return write(fd, s, len) == (ssize_t)len ? 0 : -1;
}

int main(int argc, char **argv)
{
	if (argc != 3) {
		fprintf(stderr, "usage: %s <nano> <file>\n", argv[0]);
		return 2;
	}
	const char *nano = argv[1];
	const char *file = argv[2];
	remove(file);

	int mfd;
	struct winsize ws = { 24, 80, 0, 0 };
	pid_t pid = forkpty(&mfd, NULL, NULL, &ws);
	if (pid < 0) {
		perror("forkpty");
		return 2;
	}
	if (pid == 0) {
		setenv("TERM", "xterm", 1);
		setenv("TERMINFO", "/nonexistent", 1);
		setenv("TERMINFO_DIRS", "/nonexistent", 1);
		setenv("LANG", "C.UTF-8", 1);
		execl(nano, nano, file, (char *)NULL);
		perror("execl");
		_exit(127);
	}

	drain(mfd, 700);            /* let nano paint its initial screen */
	if (send(mfd, "Hello Fil-C nano"))
		goto fail;
	drain(mfd, 300);
	if (send(mfd, "\x0F"))      /* ^O -- Write Out */
		goto fail;
	drain(mfd, 300);
	if (send(mfd, "\r"))        /* confirm the pre-filled file name */
		goto fail;
	drain(mfd, 400);
	if (send(mfd, "\x18"))      /* ^X -- Exit */
		goto fail;
	drain(mfd, 400);

	/* Wait up to ~3s for a clean exit, then give up and kill it. */
	int status = 0, exited = 0;
	for (int i = 0; i < 30; i++) {
		if (waitpid(pid, &status, WNOHANG) == pid) {
			exited = 1;
			break;
		}
		nap(100);
	}
	if (!exited) {
		kill(pid, SIGKILL);
		waitpid(pid, NULL, 0);
		fprintf(stderr, "\nsmoke: nano did not exit on its own\n");
		return 1;
	}
	if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
		fprintf(stderr, "\nsmoke: nano exited abnormally (%d)\n", status);
		return 1;
	}

	FILE *f = fopen(file, "rb");
	if (!f) {
		fprintf(stderr, "\nsmoke: %s was never written\n", file);
		return 1;
	}
	char got[256] = { 0 };
	size_t n = fread(got, 1, sizeof got - 1, f);
	fclose(f);
	if (n != strlen(EXPECTED) || memcmp(got, EXPECTED, n) != 0) {
		fprintf(stderr, "\nsmoke: file content mismatch: %zu bytes [%s]\n", n, got);
		return 1;
	}

	fprintf(stderr, "\nsmoke: nano edited and saved a file using only compiled-in terminfo\n");
	return 0;

fail:
	kill(pid, SIGKILL);
	waitpid(pid, NULL, 0);
	fprintf(stderr, "\nsmoke: failed to send keystrokes to nano\n");
	return 1;
}
