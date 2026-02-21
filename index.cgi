#!/usr/bin/env perl

package main;


use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require './zfsguru_i18n.pl';
require 'ui-lib.pl';

# Parse CGI params
zfsguru_readparse();
main::zfsguru_init('en');

main::zfsguru_page_header(title_key => "TITLE_DASHBOARD");

eval { acl_require_feature('overview'); };
if ($@) {
    print &ui_print_error(main::L("ERR_ACCESS_DENIED_FEATURE", 'overview'));
    main::zfsguru_page_footer(url => "/");
    exit 0;
}

print "<div style='display:flex;align-items:center;gap:14px;margin:8px 0 12px 0;padding:10px 12px;border:1px solid #d7dbe0;border-radius:6px;background:#f7fafc;max-width:680px'>\n";
print "  <div style='width:192px;height:144px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;border:1px solid #bfc8d3;border-radius:4px;background:#fff;overflow:hidden;box-shadow:inset 0 0 0 1px #eef3f8'>\n";
print "    <img src='images/zfsguru_4_3.jpg' alt='ZFSguru' style='width:100%;height:100%;object-fit:cover;display:block'>\n";
print "  </div>\n";
print "  <div>\n";
print "    <div style='font-size:20px;font-weight:700;color:#0b2f4d;line-height:1.2'>" . main::L("SUB_DASHBOARD") . "</div>\n";
print "    <div style='margin-top:2px;font-size:13px;color:#52657a'>Pools, datasets and services at a glance.</div>\n";
print "  </div>\n";
print "</div>\n";

my $pools = zpool_list();

my @qa_storage = (
    [ 'advanced_pools.cgi?action=list',    main::L("QA_POOL_MANAGEMENT") ],
    [ 'advanced_datasets.cgi?action=list', main::L("QA_DATASET_MANAGEMENT") ],
    [ 'disks.cgi?action=list',             main::L("QA_DISKS_HARDWARE") ],
    [ 'zfsaclmanager.cgi',                 main::L("QA_ZFS_ACL_MANAGER") ],
);
my @qa_services = (
    [ 'services.cgi?action=manage',    main::L("QA_SERVICES") ],
    [ 'network.cgi?action=interfaces', main::L("QA_NETWORK") ],
    [ 'system.cgi?action=preferences', main::L("QA_SYSTEM") ],
    [ 'status.cgi?action=overview',    main::L("QA_SYSTEM_OVERVIEW") ],
);
my @qa_access = (
    [ 'access.cgi?action=smb_shares', main::L("QA_ACCESS") ],
    [ 'acl.cgi?action=view',          main::L("QA_ACCESS_CONTROL") ],
    [ 'system.cgi?action=preferences&prefs_tab=config', main::L("QA_SYSTEM_PREFERENCES") ],
    [ 'uefi.cgi?action=list',         main::L("QA_UEFI_ESP") ],
);

print "<div class='zfsguru-quickaccess-panel'>\n";
print "  <div class='zfsguru-quickaccess-head'>\n";
print "    <span>" . main::L("SUB_QUICK_ACCESS") . "</span>\n";
print "  </div>\n";

print "  <div class='zfsguru-quickaccess-group'>\n";
print "    <div class='zfsguru-quickaccess-title'>" . main::L("QA_GROUP_STORAGE") . "</div>\n";
print "    <div class='zfsguru-quickaccess'>\n";
print join("\n", map { my ($u,$l)=@$_; qq(<a class="zfsguru-qa-btn" href=").&html_escape($u).qq(">).&html_escape($l).qq(</a>) } @qa_storage) . "\n";
print "    </div>\n";
print "  </div>\n";

print "  <div class='zfsguru-quickaccess-group'>\n";
print "    <div class='zfsguru-quickaccess-title'>" . main::L("QA_GROUP_SERVICES") . "</div>\n";
print "    <div class='zfsguru-quickaccess'>\n";
print join("\n", map { my ($u,$l)=@$_; qq(<a class="zfsguru-qa-btn" href=").&html_escape($u).qq(">).&html_escape($l).qq(</a>) } @qa_services) . "\n";
print "    </div>\n";
print "  </div>\n";

print "  <div class='zfsguru-quickaccess-group'>\n";
print "    <div class='zfsguru-quickaccess-title'>" . main::L("QA_GROUP_ACCESS") . "</div>\n";
print "    <div class='zfsguru-quickaccess'>\n";
print join("\n", map { my ($u,$l)=@$_; qq(<a class="zfsguru-qa-btn" href=").&html_escape($u).qq(">).&html_escape($l).qq(</a>) } @qa_access) . "\n";
print "    </div>\n";
print "  </div>\n";
print "</div>\n";

print &ui_hr();

print &ui_table_start(main::L("TABLE_POOLS_SUMMARY"), "width=100% style='max-width:680px'", 2);
my $pool_count = scalar(@$pools) || 0;
print &ui_table_span("<b>" . &html_escape(main::L("ROW_TOTAL_POOLS")) . ":</b> " . &html_escape($pool_count));
if (@$pools) {
    my @pool_blocks;
    for my $p (@$pools) {
        my $name = $p->{name} || '';
        next unless length $name;
        my $pool_url = "advanced_pools.cgi?action=view&pool=" . &url_encode($name);
        my $pool_link = &ui_link($pool_url, &html_escape($name), "zfsguru-pool-link");

        my $health = uc($p->{health} || 'UNKNOWN');
        my ($needs_attention, $attention_msg) = pool_needs_attention($name, $health);
        my $health_html;
        if ($needs_attention && $health eq 'ONLINE') {
            my $safe_msg = &html_escape($attention_msg || '');
            my $title_attr = $safe_msg ne '' ? " title='$safe_msg'" : '';
            $health_html = "<span class='zfsguru-status-warn zfsguru-status-badge'$title_attr>" .
                           "ONLINE<br><span class='zfsguru-status-note'>Action required!</span></span>";
        } else {
            my $health_cls =
                $health eq 'ONLINE' ? 'zfsguru-status-ok' :
                $health eq 'DEGRADED' ? 'zfsguru-status-warn' :
                $health eq 'UNKNOWN' ? 'zfsguru-status-unknown' :
                'zfsguru-status-bad';
            $health_html = "<span class='$health_cls'>" . &html_escape($health) . "</span>";
        }

        my $info = "<span style='display:inline-block;max-width:300px'>" .
                   &html_escape($p->{size} || '-') .
                   " / " . &html_escape($p->{alloc} || '-') .
                   " / " . &html_escape($p->{free} || '-') .
                   " / " . $health_html .
                   "</span>";
        push @pool_blocks,
            "<div style='margin:0 0 12px 0'>" .
            "<div>" . $pool_link . "</div>" .
            "<div style='margin-top:2px'>" . $info . "</div>" .
            "</div>";
    }

    if (@pool_blocks) {
        my $half = int((scalar(@pool_blocks) + 1) / 2);
        my $left_col  = join('', @pool_blocks[0 .. $half - 1]);
        my $right_col = $half < scalar(@pool_blocks)
            ? join('', @pool_blocks[$half .. $#pool_blocks])
            : '&nbsp;';
        my $two_col_html =
            "<div style='display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:24px'>" .
            "<div>$left_col</div>" .
            "<div>$right_col</div>" .
            "</div>";
        print &ui_table_row('', $two_col_html);
    } else {
        print &ui_table_row("", main::L("ERR_NO_POOLS_READABLE"));
    }
} else {
    print &ui_table_row("", main::L("ERR_NO_POOLS_READABLE"));
}
print &ui_table_end();

main::zfsguru_page_footer(url => "/");

sub pool_needs_attention {
    my ($pool_name, $health) = @_;
    return (0, '') unless defined $pool_name && is_pool_name($pool_name);
    return (1, 'Pool health is not ONLINE') if defined($health) && $health ne '' && $health ne 'ONLINE';

    my ($rc, $out, $err) = run_cmd(($zfsguru_lib::ZPOOL || '/sbin/zpool'), 'status', $pool_name);
    return (0, '') if $rc != 0 || !$out;

    my $state = '';
    my $status = '';
    my $in_status = 0;
    for my $line (split /\n/, $out) {
        if ($line =~ /^\s*state:\s*(.+?)\s*$/i) {
            $state = $1;
            next;
        }
        if ($line =~ /^\s*status:\s*(.*?)\s*$/i) {
            $status = $1;
            $in_status = 1;
            next;
        }
        if ($in_status) {
            last if $line =~ /^\s*(?:action|scan|config|errors|see):/i;
            last if $line =~ /^\S/;
            $line =~ s/^\s+//;
            $status .= " $line" if length $line;
        }
    }
    $status =~ s/\s+/ /g;
    $status =~ s/^\s+|\s+$//g;

    if ($state ne '' && uc($state) ne 'ONLINE') {
        return (1, $status || "state: $state");
    }
    if ($status =~ /\b(?:degraded|fault|error|offline|unavail|removed|corrupt|suspended|insufficient)\b/i) {
        return (1, $status);
    }
    return (0, $status);
}
