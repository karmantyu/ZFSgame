# Shared i18n and UI helpers for ZFSguru CGIs.

package main;

use strict;
use warnings;

our (%text, %_loaded_lang);
our $zfsguru_assets_added;
our $zfsguru_assets_body_added;

sub zfsguru_module_base_url {
    my $sn = $ENV{'SCRIPT_NAME'} || '';
    if ($sn =~ m{^(/[^/]+)/[^/]+$}) {
        return $1;
    }
    if (defined &get_webprefix && defined &get_module_name) {
        my $wp = get_webprefix();
        my $mn = get_module_name();
        if (defined $wp && defined $mn && $mn ne '') {
            $wp ||= '';
            return $wp . '/' . $mn;
        }
    }
    return '/ZFSguru';
}

sub load_text_file {
    my ($lang) = @_;
    $lang ||= 'en';
    return if $_loaded_lang{$lang};

    my $path = "./lang/$lang";
    return unless -r $path;

    open my $fh, '<', $path or return;
    while (<$fh>) {
        chomp;
        next if /^\s*#/;
        next if /^\s*$/;
        next unless /^([^=]+)=(.*)$/;

        my ($k, $v) = ($1, $2);
        $v =~ s/^\s+|\s+$//g;
        $v =~ s/\$\{?NL\}?/\n/g;
        $text{$k} = $v;
    }
    close $fh;

    $_loaded_lang{$lang} = 1;
}

sub zfsguru_init {
    my ($lang) = @_;
    $lang ||= 'en';
    load_text_file($lang);
    zfsguru_install_ui_fallbacks();
    return 1;
}

sub _zfsguru_html_escape {
    my ($s) = @_;
    $s = '' unless defined $s;
    $s =~ s/&/&amp;/g;
    $s =~ s/</&lt;/g;
    $s =~ s/>/&gt;/g;
    $s =~ s/"/&quot;/g;
    $s =~ s/'/&#39;/g;
    return $s;
}

sub zfsguru_install_ui_fallbacks {
    no strict 'refs';
    no warnings 'redefine';

    if (!defined &main::ui_print_error) {
        *main::ui_print_error = sub {
            my ($msg) = @_;
            if (defined &WebminCore::ui_print_error) {
                return WebminCore::ui_print_error($msg);
            }
            return "<div class='zfsguru-msg zfsguru-msg-error'><b>Error:</b> " .
                   _zfsguru_html_escape($msg) . "</div>";
        };
    }

    if (!defined &main::ui_print_success) {
        *main::ui_print_success = sub {
            my ($msg) = @_;
            if (defined &WebminCore::ui_print_success) {
                return WebminCore::ui_print_success($msg);
            }
            return "<div class='zfsguru-msg zfsguru-msg-success'><b>Success:</b> " .
                   _zfsguru_html_escape($msg) . "</div>";
        };
    }

    if (!defined &main::ui_print_error_header) {
        *main::ui_print_error_header = sub {
            my ($msg) = @_;
            return "<h3 style='color:#a00000'>" . _zfsguru_html_escape($msg) . "</h3>";
        };
    }
}

sub zfsguru_add_common_assets {
    return if $zfsguru_assets_added;
    my $base = zfsguru_module_base_url();
    my $css = $base . "/zfsguru.css";
    my $js  = $base . "/zfsguru.js";
    my $addh;
    if (defined &add_header) {
        $addh = \&add_header;
    }
    elsif (defined &main::add_header) {
        $addh = \&main::add_header;
    }
    elsif (defined &WebminCore::add_header) {
        $addh = \&WebminCore::add_header;
    }
    if ($addh) {
        my $safe_css = &html_escape($css || '');
        my $safe_js = &html_escape($js || '');
        $addh->("<link rel='stylesheet' href='$safe_css'>");
        $addh->("<script src='$safe_js'></script>");
    }
    $zfsguru_assets_added = 1;
}

sub zfsguru_print_assets_fallback {
    return if $zfsguru_assets_body_added;
    my $base = zfsguru_module_base_url();
    my $safe_base = &html_escape($base || '');
    print "<link rel='stylesheet' href='$safe_base/zfsguru.css'>\n";
    print "<script src='$safe_base/zfsguru.js'></script>\n";
    $zfsguru_assets_body_added = 1;
}

sub L {
    my ($key, @args) = @_;
    my $tmpl = exists $text{$key} ? $text{$key} : $key;

    for my $i (1 .. 9) {
        my $pat = '\\$' . $i;
        my $rep = defined $args[$i - 1] ? $args[$i - 1] : '';
        $tmpl =~ s/$pat/$rep/g;
    }

    my $arg0 = defined $args[0] ? $args[0] : '';
    $tmpl =~ s/%ERROR%/$arg0/g;
    $tmpl =~ s/%POOL%/$arg0/g;
    return $tmpl;
}

sub zfsguru_msg_error {
    my ($msg) = @_;
    return "<div class='zfsguru-msg zfsguru-msg-error'><b>Error:</b> " . &html_escape($msg // '') . "</div>";
}

sub zfsguru_msg_success {
    my ($msg) = @_;
    return "<div class='zfsguru-msg zfsguru-msg-success'><b>Success:</b> " . &html_escape($msg // '') . "</div>";
}

sub zfsguru_print_tabs {
    my (%opt) = @_;
    my $script = $opt{script} || '';
    my $active = defined $opt{active} ? $opt{active} : '';
    my $tabs   = $opt{tabs} || [];
    my $param  = $opt{param} || 'action';

    my $xnavigation = '';
    if (defined $main::in{'xnavigation'} && $main::in{'xnavigation'} =~ /^\d+$/) {
        $xnavigation = "&xnavigation=$main::in{'xnavigation'}";
    }

    my $html = "<div class='zfsguru-tabs'>\n";
    my $join = index($script, '?') >= 0 ? '&' : '?';
    for my $tab (@$tabs) {
        my ($id, $label_key) = @$tab;
        my $label = &html_escape(L($label_key));
        my $classes = $id eq $active ? 'zfsguru-tab zfsguru-tab-active' : 'zfsguru-tab';
        my $href = &html_escape($script . $join . $param . "=" . $id . $xnavigation);
        $html .= "<a href='$href' class='" . &html_escape($classes) . "'>$label</a>\n";
    }
    $html .= "</div>\n";
    return $html;
}

sub zfsguru_page_header {
    my (%opt) = @_;
    my $title = $opt{title_key} ? L($opt{title_key}) : ($opt{title} || 'ZFSguru');
    my $with_help = exists $opt{with_help} ? $opt{with_help} : 1;
    my $rightside = $opt{rightside};

    zfsguru_add_common_assets();

    if (!defined $rightside && $with_help) {
        my $btn_style = "display:inline-block;padding:4px 10px;background:#0275d8;color:#fff;border:1px solid #0275d8;border-radius:3px;text-decoration:none;font-size:12px;line-height:1.4;white-space:nowrap";
        $rightside = "<a href='about.cgi' style='$btn_style'>" . &html_escape(L('LINK_ABOUT')) . "</a>";
        $rightside .= "<br /><a href='acl.cgi?action=view' style='$btn_style'>" . &html_escape(L('QA_ACCESS_CONTROL')) . "</a>";
        $rightside .= "<br /><a href='system.cgi?action=preferences&prefs_tab=config' style='$btn_style'>" . &html_escape(L('QA_SYSTEM_PREFERENCES')) . "</a>";
        if (defined &help_search_link) {
            $rightside .= "<br />" . &help_search_link("zfs, zpool", "man", "doc", "google");
        }
    }

    my $uih;
    if (defined &ui_print_header) {
        $uih = \&ui_print_header;
    }
    elsif (defined &main::ui_print_header) {
        $uih = \&main::ui_print_header;
    }
    elsif (defined &WebminCore::ui_print_header) {
        $uih = \&WebminCore::ui_print_header;
    }

    if ($uih) {
        # Disable Webmin's built-in module-config icon to avoid config.cgi dependency,
        # and provide our own ACL/config link in right-side links.
        $uih->(undef, $title, "", undef, 0, 1, 0, $rightside);
        zfsguru_print_assets_fallback();
        return;
    }

    # Last-resort plain header to avoid CGI "Bad Header" failures.
    print "Content-type: text/html; charset=UTF-8\n\n";
    print "<html><head><title>" . &html_escape($title) . "</title></head><body>\n";
    zfsguru_print_assets_fallback();
}

sub zfsguru_page_footer {
    my (%opt) = @_;
    my $url = defined $opt{url} ? $opt{url} : 'index.cgi';
    my $label = defined $opt{label} ? $opt{label} : L('BTN_BACK');
    my $uif;
    if (defined &ui_print_footer) {
        $uif = \&ui_print_footer;
    }
    elsif (defined &main::ui_print_footer) {
        $uif = \&main::ui_print_footer;
    }
    elsif (defined &WebminCore::ui_print_footer) {
        $uif = \&WebminCore::ui_print_footer;
    }

    if ($uif) {
        $uif->($url, $label);
    } else {
        print "</body></html>\n";
    }
}

1;
