#!/usr/bin/env perl

package main;

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => "TITLE_ABOUT");

eval { acl_require_feature('overview'); };
if ($@) {
    print &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'overview'));
    zfsguru_page_footer();
    exit 0;
}

sub readme_md_safe_url {
    my ($url) = @_;
    return '' unless defined $url;
    $url =~ s/^\s+|\s+$//g;
    return '' if $url eq '';
    return $url if $url =~ m{^(?:https?://|mailto:)}i;
    return $url if $url =~ m{^(?:/|#)};
    return '';
}

sub readme_md_inline {
    my ($txt) = @_;
    $txt = '' unless defined $txt;

    my @parts = split /(`[^`]*`)/, $txt;
    my @out;
    for my $part (@parts) {
        if ($part =~ /^`([^`]*)`$/) {
            push @out, "<code>" . &html_escape($1) . "</code>";
            next;
        }

        my @chunks = split /(\[[^\]]+\]\([^)]+\))/, $part;
        my $chunk_out = '';
        for my $chunk (@chunks) {
            if ($chunk =~ /^\[([^\]]+)\]\(([^)]+)\)$/) {
                my ($label, $url) = ($1, $2);
                my $safe_url = readme_md_safe_url($url);
                if ($safe_url ne '') {
                    my $attrs = ($safe_url =~ m{^https?://}i)
                        ? " target='_blank' rel='noopener noreferrer'"
                        : '';
                    $chunk_out .= "<a class='zfsguru-link' href='" . &html_escape($safe_url) . "'$attrs>" .
                                  &html_escape($label) . "</a>";
                } else {
                    $chunk_out .= &html_escape($chunk);
                }
                next;
            }

            my $esc = &html_escape($chunk);
            $esc =~ s/\*\*([^*]+)\*\*/<strong>$1<\/strong>/g;
            $esc =~ s/\*([^*]+)\*/<em>$1<\/em>/g;
            $chunk_out .= $esc;
        }
        push @out, $chunk_out;
    }

    return join('', @out);
}

sub render_markdown_readme {
    my ($txt) = @_;
    return '' unless defined $txt && $txt ne '';

    $txt =~ s/\r\n/\n/g;
    $txt =~ s/\r/\n/g;
    my @lines = split /\n/, $txt;

    my @out;
    my $in_code = 0;
    my $list_mode = '';
    my @para;

    my $flush_para = sub {
        return unless @para;
        my @trimmed = map {
            my $s = $_;
            $s =~ s/^\s+|\s+$//g;
            $s;
        } @para;
        my $p = join(' ', @trimmed);
        $p =~ s/\s{2,}/ /g;
        push @out, "<p>" . readme_md_inline($p) . "</p>";
        @para = ();
    };

    my $close_list = sub {
        return if $list_mode eq '';
        push @out, "</$list_mode>";
        $list_mode = '';
    };

    for my $line (@lines) {
        if ($line =~ /^```/) {
            $flush_para->();
            $close_list->();
            if (!$in_code) {
                push @out, "<pre class='zfsguru-code-block'><code>";
                $in_code = 1;
            } else {
                push @out, "</code></pre>";
                $in_code = 0;
            }
            next;
        }

        if ($in_code) {
            push @out, &html_escape($line) . "\n";
            next;
        }

        if ($line =~ /^\s*$/) {
            $flush_para->();
            $close_list->();
            next;
        }

        if ($line =~ /^(#{1,6})\s+(.+?)\s*$/) {
            $flush_para->();
            $close_list->();
            my $lvl = length($1);
            $lvl = 1 if $lvl < 1;
            $lvl = 4 if $lvl > 4;
            push @out, "<h$lvl class='zfsguru-readme-h$lvl'>" . readme_md_inline($2) . "</h$lvl>";
            next;
        }

        if ($line =~ /^\s*[-*_]{3,}\s*$/) {
            $flush_para->();
            $close_list->();
            push @out, "<hr class='zfsguru-readme-hr'>";
            next;
        }

        if ($line =~ /^\s*[-*+]\s+(.+?)\s*$/) {
            $flush_para->();
            if ($list_mode ne 'ul') {
                $close_list->();
                push @out, "<ul class='zfsguru-readme-list'>";
                $list_mode = 'ul';
            }
            push @out, "<li>" . readme_md_inline($1) . "</li>";
            next;
        }

        if ($line =~ /^\s*\d+\.\s+(.+?)\s*$/) {
            $flush_para->();
            if ($list_mode ne 'ol') {
                $close_list->();
                push @out, "<ol class='zfsguru-readme-list'>";
                $list_mode = 'ol';
            }
            push @out, "<li>" . readme_md_inline($1) . "</li>";
            next;
        }

        $close_list->();
        push @para, $line;
    }

    $flush_para->();
    $close_list->();
    push @out, "</code></pre>" if $in_code;

    return "<div class='zfsguru-readme-rendered'>" . join("\n", @out) . "</div>";
}

my %mod = (
    desc          => 'ZFSguru Webmin Module',
    version       => 'unknown',
    author        => 'ZFSguru Contributors',
    authorurl     => '',
    license       => 'unknown',
    os_support    => '',
    webminversion => '',
);

my $module_info_path = "$Bin/module.info";
if (open(my $fh, '<', $module_info_path)) {
    while (my $line = <$fh>) {
        chomp $line;
        $line =~ s/\r$//;
        next if $line =~ /^\s*#/;
        next unless $line =~ /^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/;
        my ($k, $v) = (lc($1), $2);
        next unless exists $mod{$k};
        $mod{$k} = $v;
    }
    close($fh);
}

print &ui_subheading(L("SUB_ABOUT"));
print "<p>" . L("MSG_ABOUT_TEXT") . "</p>";

print &ui_table_start(L("TABLE_ABOUT"), "width=100%", 2);
print &ui_table_row(L("ROW_PRODUCT_NAME"), &html_escape($mod{desc}));
print &ui_table_row(L("ROW_MODULE_VERSION"), &html_escape($mod{version}));
print &ui_table_row(L("ROW_AUTHOR"), &html_escape($mod{author}));
print &ui_table_row(L("ROW_WEBSITE"), &html_escape($mod{authorurl}));
print &ui_table_row(L("ROW_LICENSE"), &html_escape($mod{license}));
print &ui_table_row(L("ROW_OS_SUPPORT"), &html_escape($mod{os_support} || L("VALUE_UNKNOWN")));
print &ui_table_row(L("ROW_WEBMIN_VERSION"), &html_escape($mod{webminversion} || L("VALUE_UNKNOWN")));
print &ui_table_end();

my $about_path = "$Bin/ABOUT.en.md";
my $about_text = '';
if (-r $about_path) {
    $about_text = read_file_text($about_path);
}

print &ui_subheading("User Guide");
if (defined $about_text && $about_text ne '') {
    print render_markdown_readme($about_text);
} else {
    print &ui_alert("ABOUT.en.md not found", 'warning');
}

my $readme_path = "$Bin/README.md";
my $readme_text = '';
if (-r $readme_path) {
    $readme_text = read_file_text($readme_path);
}

print &ui_subheading(L("SUB_README"));
if (defined $readme_text && $readme_text ne '') {
    print render_markdown_readme($readme_text);
} else {
    print &ui_alert(L("WARN_README_NOT_FOUND"), 'warning');
}

zfsguru_page_footer();

