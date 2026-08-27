#!/usr/bin/perl
# Drop only the lines whose IRI REFERENCES are malformed, and count them.
#
# The defect (13,556 lines in freebase-links) is a string quote inside an IRI:
#     <http://dbpedia.org/resource/Zsuzsanna_"Susan"_Polgar> <...> <...> .
# Turtle forbids '"' inside <...>, so QLever aborts the whole index build with
# "Unterminated IRI reference".
#
# Why this is not a regex. A crude /<[^>]*"/ also matches perfectly legal Turtle
# where the '<' sits INSIDE a literal:
#     <...16th_Lok_Sabha> <...label> "Assets <"@en .
#     <...Ahmed_Shafik>   <...name>  "<span"@en .
# A full scan of all 86 input files found 15,273 such regex hits but only 13,556
# real defects -- so a regex filter would have silently deleted 1,717 valid
# triples. It is also slow: that pattern backtracks on DBpedia's long literals,
# taking ~25 min for one file.
#
# So: locate candidate lines with index() (no backtracking), then decide each
# candidate with an exact left-to-right scan that tracks literal vs IRI state.
#
# Usage:  ... | perl iri_filter.pl [reject-file]   (stats go to STDERR)
use strict;
use warnings;

my $reject_path = shift;
my $rej;
if (defined $reject_path) {
    open($rej, '>', $reject_path) or die "cannot write $reject_path: $!";
}

my ($kept, $dropped) = (0, 0);

# Fast candidate test: walk the IRI tokens with index(). A line is a candidate
# only if some '<' has a '"' before its closing '>'. Ordinary triples exit after
# a handful of index() calls and never reach the exact scan.
sub is_candidate {
    my ($line) = @_;
    my $pos = 0;
    while ((my $lt = index($line, '<', $pos)) >= 0) {
        my $gt = index($line, '>', $lt + 1);
        my $q  = index($line, '"', $lt + 1);
        return 1 if $q >= 0 && ($gt < 0 || $q < $gt);   # quote before the '>'
        return 0 if $gt < 0;
        $pos = $gt + 1;
    }
    return 0;
}

# Exact decision: is a '"' actually inside an IRI, or just inside a literal?
sub malformed {
    my ($line) = @_;
    my ($in_literal, $in_iri, $escaped) = (0, 0, 0);
    for my $c (split //, $line) {
        if ($escaped)    { $escaped = 0; next }
        if ($c eq '\\')  { $escaped = 1; next }
        if ($in_literal) { $in_literal = 0 if $c eq '"'; next }
        if ($in_iri) {
            return 1 if $c eq '"' || $c eq '<';   # illegal inside an IRIREF
            $in_iri = 0 if $c eq '>';
            next;
        }
        if ($c eq '"')   { $in_literal = 1; next }
        if ($c eq '<')   { $in_iri = 1;     next }
    }
    return $in_iri;   # ended the line still inside an IRI
}

while (my $line = <STDIN>) {
    if (is_candidate($line) && malformed($line)) {
        $dropped++;
        print $rej $line if defined $rej;
    } else {
        $kept++;
        print $line;
    }
}
close $rej if defined $rej;
printf STDERR "iri_filter: kept %d lines, dropped %d malformed\n", $kept, $dropped;
