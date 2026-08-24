#!/usr/bin/env perl

use strict;
use warnings;

use constant PTR_ALIGN => 8;

my $die = qr/^\s*<(\d+)><([0-9a-f]+)>: Abbrev Number: \d+ \((DW_TAG_\w+)\)/;
my $attr_name = qr/DW_AT_name\s*:\s*(?:\(.*?\)\s*:\s*)?(\S+)/;
my $attr_type = qr/DW_AT_type\s*:\s*<0x([0-9a-f]+)>/;
my $attr_location = qr/DW_AT_data_member_location:\s*(\d+)/;

sub scan {
    my ($binary) = @_;
    open my $readelf, '-|', 'readelf', '--debug-dump=info', $binary
        or die "cannot run readelf for $binary: $!\n";
    my @lines = <$readelf>;
    close $readelf or die "readelf failed for $binary\n";

    my (%kind, %type_reference);
    my $has_debug_info = 0;
    my $current;
    for my $line (@lines) {
        if ($line =~ $die) {
            $has_debug_info = 1;
            $current = hex $2;
            $kind{$current} = $3;
            next;
        }
        if (defined $current && $line =~ $attr_type) {
            $type_reference{$current} = hex $1;
        }
    }

    my $is_pointer = sub {
        my ($offset) = @_;
        for (1 .. 16) {
            my $die_kind = $kind{$offset};
            return 1 if defined $die_kind && $die_kind eq 'DW_TAG_pointer_type';
            return 0 unless defined $die_kind && $die_kind =~
                /^DW_TAG_(?:typedef|const_type|volatile_type|restrict_type|atomic_type)$/;
            return 0 unless exists $type_reference{$offset};
            $offset = $type_reference{$offset};
        }
        return 0;
    };

    my %findings;
    my $index = 0;
    while ($index < @lines) {
        my $line = $lines[$index];
        if ($line !~ $die || ($3 ne 'DW_TAG_structure_type' &&
                $3 ne 'DW_TAG_class_type')) {
            ++$index;
            next;
        }

        my $depth = $1;
        my $structure_name;
        my $child = $index + 1;
        while ($child < @lines) {
            my $child_line = $lines[$child];
            if ($child_line =~ $die) {
                my ($child_depth, $child_kind) = ($1, $3);
                last if $child_depth <= $depth;
                if ($child_depth == $depth + 1 && $child_kind eq 'DW_TAG_member') {
                    my ($member_name, $member_offset, $member_type);
                    my $attribute = $child + 1;
                    while ($attribute < @lines && $lines[$attribute] !~ $die) {
                        my $attribute_line = $lines[$attribute];
                        $member_name = $1
                            if !defined $member_name && $attribute_line =~ $attr_name;
                        $member_offset = $1
                            if !defined $member_offset && $attribute_line =~ $attr_location;
                        $member_type = hex $1
                            if !defined $member_type && $attribute_line =~ $attr_type;
                        ++$attribute;
                    }
                    if (defined $member_offset && defined $member_type &&
                            $member_offset % PTR_ALIGN && $is_pointer->($member_type)) {
                        my $key = join "\0", $structure_name // '<anon>',
                            $member_name // '<anon>', $member_offset;
                        $findings{$key} = 1;
                    }
                }
            } elsif (!defined $structure_name && $child_line =~ $attr_name) {
                $structure_name = $1;
            }
            ++$child;
        }
        $index = $child > $index ? $child : $index + 1;
    }

    return ($has_debug_info, sort keys %findings);
}

my $failed = 0;
my $missing_debug_info = 0;
for my $binary (@ARGV) {
    my ($has_debug_info, @findings) = scan($binary);
    (my $name = $binary) =~ s{.*/}{};
    if (!$has_debug_info) {
        print STDERR "$name: no DWARF debug info\n";
        $missing_debug_info = 1;
        next;
    }
    print "$name: ", scalar @findings, " misaligned pointer field(s)\n";
    for my $finding (@findings) {
        my ($structure, $member, $offset) = split /\0/, $finding;
        print "  $structure.$member \@ offset $offset\n";
    }
    $failed ||= @findings != 0;
}

exit 2 if $missing_debug_info;
exit $failed;
