#!/usr/bin/env perl
use strict;
use warnings;
require './zfsaclmanager-lib.pl';
our (%in, %text);

&ReadParse();

my $title = $text{'aclm_title'} || 'ZFS ACL Manager';
my $page_title = 'ZFS ACL Manager README';
my $readme_file = 'Readme_zfsacl.md';
my $content = '';

sub _render_md_like
{
    my ($md) = @_;
    return '' if (!defined $md || $md eq '');

    my @lines = split(/\r?\n/, $md);
    my $html = '';
    my $in_ul = 0;
    my $in_ol = 0;
    my $in_code = 0;

    my $close_lists = sub {
        if ($in_ul) { $html .= "</ul>\n"; $in_ul = 0; }
        if ($in_ol) { $html .= "</ol>\n"; $in_ol = 0; }
    };

    foreach my $line (@lines) {
        if ($line =~ /^\s*```/) {
            $close_lists->();
            if ($in_code) {
                $html .= "</code></pre>\n";
                $in_code = 0;
            }
            else {
                $html .= "<pre style='white-space:pre-wrap;word-break:break-word'><code>";
                $in_code = 1;
            }
            next;
        }
        if ($in_code) {
            $html .= &html_escape($line)."\n";
            next;
        }

        if ($line =~ /^\s*###\s+(.*)$/) {
            $close_lists->();
            $html .= "<h4 style='margin:10px 0 6px 0'>".&html_escape($1)."</h4>\n";
            next;
        }
        if ($line =~ /^\s*##\s+(.*)$/) {
            $close_lists->();
            $html .= "<h3 style='margin:14px 0 8px 0'>".&html_escape($1)."</h3>\n";
            next;
        }
        if ($line =~ /^\s*#\s+(.*)$/) {
            $close_lists->();
            $html .= "<h2 style='margin:16px 0 10px 0'>".&html_escape($1)."</h2>\n";
            next;
        }

        if ($line =~ /^\s*-\s+(.*)$/) {
            if ($in_ol) { $html .= "</ol>\n"; $in_ol = 0; }
            if (!$in_ul) { $html .= "<ul style='margin:6px 0 10px 20px'>\n"; $in_ul = 1; }
            $html .= "<li>".&html_escape($1)."</li>\n";
            next;
        }
        if ($line =~ /^\s*\d+\.\s+(.*)$/) {
            if ($in_ul) { $html .= "</ul>\n"; $in_ul = 0; }
            if (!$in_ol) { $html .= "<ol style='margin:6px 0 10px 20px'>\n"; $in_ol = 1; }
            $html .= "<li>".&html_escape($1)."</li>\n";
            next;
        }

        if ($line =~ /^\s*$/) {
            $close_lists->();
            $html .= "<div style='height:6px'></div>\n";
            next;
        }

        $close_lists->();
        $html .= "<p style='margin:4px 0'>".&html_escape($line)."</p>\n";
    }

    $close_lists->();
    if ($in_code) {
        $html .= "</code></pre>\n";
    }
    return $html;
}

if (-r $readme_file) {
    if (open(my $fh, '<', $readme_file)) {
        local $/ = undef;
        $content = <$fh>;
        close($fh);
    }
}

$content = "README file not found: $readme_file\n" if ($content eq '');

&ui_print_header(undef, $page_title, "");

print &ui_subheading($page_title);
print &ui_table_start('Module Documentation', undef, 1);
print &ui_table_row('',
    _render_md_like($content));
print &ui_table_end();

print &ui_form_start('zfsaclmanager.cgi', 'get');
print &ui_form_end([ [ 'back', $text{'aclm_back'} || 'Back' ] ]);

&ui_print_footer('zfsaclmanager.cgi', $title);
