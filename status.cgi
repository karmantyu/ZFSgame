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
use Sys::Hostname;

# Parse CGI params
zfsguru_readparse();
zfsguru_init('en');

my $action = $in{'action'} || 'overview';
if ($action eq 'live_vmstat_partial') {
    print "Content-type: text/html; charset=UTF-8\n\n";
    eval { acl_require_feature('status'); };
    if ($@) {
        print &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'status'));
        exit 0;
    }
    action_live_vmstat(1);
    exit 0;
}

zfsguru_page_header(title_key => "TITLE_STATUS");

eval { acl_require_feature('status'); };
if ($@) {
    print &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'status'));
    zfsguru_page_footer();
    exit 0;
}

my $status_script = '/ZFSguru/status.cgi';

# Plain anchor tabs for reliable switching (works with &ReadParse)
my @tabs_list = (
    [ 'overview',  'TAB_OVERVIEW' ],
    [ 'cpu',       'TAB_CPU' ],
    [ 'memory',    'TAB_MEMORY_STATUS' ],
    [ 'live_vmstat', 'TAB_LIVE_VMSTAT' ],
    [ 'hardware',  'TAB_HARDWARE' ],
    [ 'pools',     'TAB_POOL_STATUS' ],
    [ 'health',    'TAB_HEALTH_REPORT' ],
    [ 'logs',      'TAB_SYSTEM_LOGS' ],
);

print zfsguru_print_tabs(
    script => $status_script,
    active => $action,
    tabs   => \@tabs_list,
);

if ($action eq 'overview') { &action_overview(); }
elsif ($action eq 'cpu') { &action_cpu(); }
elsif ($action eq 'memory') { &action_memory(); }
elsif ($action eq 'live_vmstat') { &action_live_vmstat(); }
elsif ($action eq 'hardware') { &action_hardware(); }
elsif ($action eq 'pools') { &action_pools(); }
elsif ($action eq 'health') { &action_health(); }
elsif ($action eq 'logs') { &action_logs(); }
else { &action_overview(); }

my $back_url = 'index.cgi';
if ($action ne 'overview') {
    $back_url = $status_script . '?action=overview';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub cap_pct_value {
    my ($raw) = @_;
    return 0 unless defined $raw;
    $raw =~ s/%$//;
    return ($raw =~ /^\d+(?:\.\d+)?$/) ? $raw + 0 : 0;
}

sub sysctl_val {
    my ($name) = @_;
    return undef unless defined $name && $name =~ /^[A-Za-z0-9_.]+$/;
    my $sysctl = $zfsguru_lib::SYSCTL || 'sysctl';
    my ($rc, $out, $err) = run_cmd($sysctl, '-n', $name);
    return undef if $rc != 0;
    $out = '' unless defined $out;
    $out =~ s/\s+$//;
    return $out;
}

sub sysctl_num {
    my ($name) = @_;
    my $v = sysctl_val($name);
    return undef unless defined $v;
    $v =~ s/^\s+|\s+$//g;
    return undef unless $v =~ /^\d+(?:\.\d+)?$/;
    return $v + 0;
}

sub parse_loadavg {
    my ($txt) = @_;
    return (undef, undef, undef) unless defined $txt;
    $txt =~ s/[{}]//g;
    $txt =~ s/,/ /g;
    my @n = grep { length $_ } split /\s+/, $txt;
    return (undef, undef, undef) unless @n >= 3;
    return (undef, undef, undef) unless $n[0] =~ /^\d/ && $n[1] =~ /^\d/ && $n[2] =~ /^\d/;
    return (sprintf("%.2f", $n[0] + 0), sprintf("%.2f", $n[1] + 0), sprintf("%.2f", $n[2] + 0));
}

sub top_cpu_pct {
    my ($top_out) = @_;
    return undef unless defined $top_out && length $top_out;
    for my $line (split /\n/, $top_out) {
        next unless $line =~ /^CPU:\s*(.+)$/i;
        my $rest = $1;
        my %p;
        while ($rest =~ /(\d+(?:\.\d+)?)%\s*([A-Za-z]+)/g) {
            my ($v, $k) = ($1 + 0, lc($2));
            $k = 'interrupt' if $k eq 'intr';
            $p{$k} = $v;
        }
        return \%p if %p;
    }
    return undef;
}

sub clamp_pct {
    my ($v) = @_;
    $v = 0 unless defined $v && $v =~ /^\d+(?:\.\d+)?$/;
    $v = 0 if $v < 0;
    $v = 100 if $v > 100;
    return $v + 0;
}

sub render_bar {
    my (%opt) = @_;
    my $pct = clamp_pct($opt{pct});
    my $label = defined $opt{label} ? $opt{label} : '';
    my $kind = defined $opt{kind} ? $opt{kind} : 'ok';
    $kind = 'ok' if $kind !~ /^(ok|warn|bad)$/;
    my $pct_txt = sprintf("%.1f", $pct) . '%';
    my $fill_cls = "zfsguru-bar-fill zfsguru-bar-fill-$kind";
    my $safe_label = &html_escape($label);
    return "<div class='zfsguru-bar' title='$pct_txt'>".
           "<div class='$fill_cls' style='width: $pct%'></div>".
           "<div class='zfsguru-bar-text'>$safe_label</div>".
           "</div>";
}

sub plain_size {
    my ($bytes) = @_;
    my $s = &nice_size($bytes);
    $s = &html_strip($s) if defined $s;
    return defined $s ? $s : L("VALUE_UNKNOWN");
}

sub render_stackbar {
    my (%opt) = @_;
    my $segs = $opt{segments};
    return '' unless ref($segs) eq 'ARRAY' && @$segs;

    my $sum = 0;
    for my $s (@$segs) {
        next unless ref($s) eq 'HASH';
        my $p = $s->{pct};
        next unless defined $p && $p =~ /^\d+(?:\.\d+)?$/;
        $sum += $p;
    }

    my $scale = ($sum > 0) ? (100 / $sum) : 1;

    my @parts;
    for my $s (@$segs) {
        next unless ref($s) eq 'HASH';
        my $pct = $s->{pct};
        next unless defined $pct && $pct =~ /^\d+(?:\.\d+)?$/;
        $pct = clamp_pct($pct);
        next if $pct <= 0;

        my $w = $pct * $scale;
        $w = 0 if $w < 0;
        $w = 100 if $w > 100;

        my $cls = $s->{class} || '';
        my $lbl = defined $s->{label} ? $s->{label} : '';
        my $title = $lbl . ": " . sprintf("%.1f%%", $pct);
        push @parts, "<div class='zfsguru-stackbar-seg $cls' style='width: $w%' title='" .
            &html_escape($title) . "'></div>";
    }

    return "<div class='zfsguru-stackbar'>" . join('', @parts) . "</div>";
}

sub render_legend {
    my (%opt) = @_;
    my $segs = $opt{segments};
    return '' unless ref($segs) eq 'ARRAY' && @$segs;

    my @items;
    for my $s (@$segs) {
        next unless ref($s) eq 'HASH';
        my $pct = $s->{pct};
        next unless defined $pct && $pct =~ /^\d+(?:\.\d+)?$/;
        $pct = clamp_pct($pct);
        next if $pct <= 0;

        my $cls = $s->{swatch_class} || '';
        my $lbl = defined $s->{label} ? $s->{label} : '';
        push @items,
            "<span class='zfsguru-legend-item'>" .
            "<span class='zfsguru-legend-swatch $cls'></span>" .
            &html_escape($lbl) . " " . &html_escape(sprintf("%.1f%%", $pct)) .
            "</span>";
    }

    return '' unless @items;
    return "<div class='zfsguru-legend'>" . join('', @items) . "</div>";
}

sub swapctl_summary {
    # Use library parser and handle both per-device rows and optional "Total" row.
    my $rows = swapctl_list();
    if ($rows && ref($rows) eq 'ARRAY' && @$rows) {
        for my $r (@$rows) {
            next unless ref($r) eq 'HASH';
            my $dev = defined($r->{device}) ? lc($r->{device}) : '';
            next unless $dev eq 'total';
            return undef unless defined($r->{total}) && $r->{total} =~ /^\d+$/;
            return undef unless defined($r->{used})  && $r->{used}  =~ /^\d+$/;
            return undef unless defined($r->{avail}) && $r->{avail} =~ /^\d+$/;
            return {
                total_bytes => ($r->{total} + 0) * 1024,
                used_bytes  => ($r->{used}  + 0) * 1024,
                avail_bytes => ($r->{avail} + 0) * 1024,
            };
        }

        my ($total_k, $used_k, $avail_k) = (0, 0, 0);
        for my $r (@$rows) {
            next unless ref($r) eq 'HASH';
            my $dev = defined($r->{device}) ? lc($r->{device}) : '';
            next if $dev eq 'total';
            next unless defined($r->{total}) && $r->{total} =~ /^\d+$/;
            next unless defined($r->{used})  && $r->{used}  =~ /^\d+$/;
            next unless defined($r->{avail}) && $r->{avail} =~ /^\d+$/;
            $total_k += ($r->{total} + 0);
            $used_k  += ($r->{used}  + 0);
            $avail_k += ($r->{avail} + 0);
        }
        if ($total_k > 0) {
            return {
                total_bytes => $total_k * 1024,
                used_bytes  => $used_k  * 1024,
                avail_bytes => $avail_k * 1024,
            };
        }
    }

    # Fallback parser for systems where swapctl output format differs.
    my $swapinfo_cmd = '/sbin/swapinfo';
    $swapinfo_cmd = '/usr/sbin/swapinfo' if !-x $swapinfo_cmd && -x '/usr/sbin/swapinfo';
    $swapinfo_cmd = 'swapinfo' if !-x $swapinfo_cmd;
    my ($rc, $out, $err) = run_cmd($swapinfo_cmd, '-k');
    if ($rc == 0 && $out) {
        my ($total_k, $used_k, $avail_k) = (0, 0, 0);
        for my $ln (split /\n/, $out) {
            next if $ln =~ /^\s*Device\b/i;
            next if $ln =~ /^\s*Total\b/i;
            next unless $ln =~ /\S/;
            my @p = split(/\s+/, $ln);
            next unless @p >= 4;
            next unless $p[1] =~ /^\d+$/ && $p[2] =~ /^\d+$/ && $p[3] =~ /^\d+$/;
            $total_k += ($p[1] + 0);
            $used_k  += ($p[2] + 0);
            $avail_k += ($p[3] + 0);
        }
        if ($total_k > 0) {
            return {
                total_bytes => $total_k * 1024,
                used_bytes  => $used_k  * 1024,
                avail_bytes => $avail_k * 1024,
            };
        }
    }

    return undef;
}

sub mem_snapshot {
    my $pagesize = sysctl_num('hw.pagesize') || sysctl_num('vm.stats.vm.v_page_size');
    my $page_count = sysctl_num('vm.stats.vm.v_page_count');
    return undef unless $pagesize && $page_count;

    my %counts;
    for my $k (qw(active inactive cache free wire laundry)) {
        my $v = sysctl_num("vm.stats.vm.v_${k}_count");
        $counts{$k} = $v if defined $v;
    }

    my $total = int($page_count * $pagesize);
    my $free  = defined $counts{free} ? int($counts{free} * $pagesize) : undef;

    my $snap = {
        pagesize    => $pagesize,
        total_bytes => $total,
        free_bytes  => $free,
        active_bytes   => defined $counts{active}   ? int($counts{active}   * $pagesize) : undef,
        inactive_bytes => defined $counts{inactive} ? int($counts{inactive} * $pagesize) : undef,
        cache_bytes    => defined $counts{cache}    ? int($counts{cache}    * $pagesize) : undef,
        wired_bytes    => defined $counts{wire}     ? int($counts{wire}     * $pagesize) : undef,
        laundry_bytes  => defined $counts{laundry}  ? int($counts{laundry}  * $pagesize) : undef,
    };

    if (defined $free) {
        my $used = $total - $free;
        $used = 0 if $used < 0;
        $snap->{used_bytes} = $used;
        $snap->{used_pct} = ($total > 0) ? (($used / $total) * 100) : 0;
    }

    my $swap = swapctl_summary();
    if ($swap) {
        $snap->{swap_total_bytes} = $swap->{total_bytes};
        $snap->{swap_used_bytes}  = $swap->{used_bytes};
        $snap->{swap_avail_bytes} = $swap->{avail_bytes};
        $snap->{swap_used_pct} = ($swap->{total_bytes} && $swap->{total_bytes} > 0)
            ? (($swap->{used_bytes} / $swap->{total_bytes}) * 100)
            : 0;
    }

    return $snap;
}

sub cpu_snapshot {
    my $snap = {};
    $snap->{model} = sysctl_val('hw.model');
    $snap->{ncpu}  = sysctl_val('hw.ncpu');

    my $load = sysctl_val('vm.loadavg');
    $snap->{load_raw} = $load if defined $load;
    my ($l1, $l5, $l15) = parse_loadavg($load);
    if (defined $l1) {
        $snap->{load1} = $l1; $snap->{load5} = $l5; $snap->{load15} = $l15;
        $snap->{load_text} = "$l1 $l5 $l15";
    } elsif (defined $load && length $load) {
        $snap->{load_text} = $load;
    }

    my ($rc, $out, $err) = run_cmd('top', '-b', '-n', '1');
    if ($rc == 0 && $out) {
        my $cpu = top_cpu_pct($out);
        if ($cpu) {
            $snap->{cpu_pct} = $cpu;
            my $idle = defined $cpu->{idle} ? $cpu->{idle} : 0;
            $idle = clamp_pct($idle);
            $snap->{busy_pct} = 100 - $idle;
        }
    }

    return $snap;
}

sub read_last_lines {
    my ($path, $max_lines) = @_;
    $max_lines = int($max_lines || 0);
    return [] unless $max_lines > 0;
    return [] unless defined $path && -r $path;

    my @buf;
    open my $fh, '<', $path or return [];
    while (my $line = <$fh>) {
        push @buf, $line;
        shift @buf while @buf > $max_lines;
    }
    close $fh;
    return \@buf;
}

sub vmstat_num {
    my ($v) = @_;
    return undef unless defined $v;
    $v =~ s/^\s+|\s+$//g;
    return undef unless $v =~ /^-?\d+(?:\.\d+)?$/;
    return $v + 0;
}

sub parse_vmstat_sample {
    my ($out) = @_;
    return undef unless defined $out && $out =~ /\S/;

    my @lines = grep { /\S/ } split /\n/, $out;
    return undef unless @lines;

    my ($sample_idx, $sample_line);
    for (my $i = $#lines; $i >= 0; $i--) {
        my $ln = $lines[$i];
        next unless $ln =~ /^\s*[-+]?\d/;
        my @tokens = grep { length $_ } split /\s+/, $ln;
        next unless @tokens >= 6;
        my $numeric = 0;
        $numeric++ for grep { /^[-+]?\d+(?:\.\d+)?$/ } @tokens;
        next unless $numeric >= int(@tokens * 0.6);
        $sample_idx = $i;
        $sample_line = $ln;
        last;
    }
    return undef unless defined $sample_line;
    my @vals = grep { length $_ } split /\s+/, $sample_line;

    my @heads;
    for (my $i = $sample_idx - 1; $i >= 0; $i--) {
        my $ln = $lines[$i];
        next unless $ln =~ /[A-Za-z]/;
        my @h = grep { length $_ } split /\s+/, $ln;
        next unless @h >= 6;
        next if $h[0] =~ /^(procs|memory|page|faults|disks|cpu)$/i;
        if (grep { lc($_) eq 'us' } @h &&
            grep { lc($_) eq 'id' } @h &&
            grep { lc($_) eq 'r' } @h) {
            @heads = @h;
            last;
        }
    }

    my %raw_map;
    if (@heads && @heads == @vals) {
        my %seen;
        for my $i (0 .. $#heads) {
            my $k = lc($heads[$i] // '');
            $k =~ s/[^a-z0-9_]+/_/g;
            $k =~ s/^_+|_+$//g;
            next if $k eq '';
            $seen{$k}++;
            my $kk = $seen{$k} > 1 ? $k . "_" . $seen{$k} : $k;
            $raw_map{$kk} = $vals[$i];
        }
    }

    my %snap = (
        raw_line  => $sample_line,
        r         => $raw_map{r},
        b         => $raw_map{b},
        w         => $raw_map{w},
        avm       => $raw_map{avm},
        fre       => $raw_map{fre},
        pi        => $raw_map{pi},
        po        => $raw_map{po},
        fr        => $raw_map{fr},
        sr        => $raw_map{sr},
        intr      => $raw_map{in},
        syscalls  => $raw_map{sy},
        cs        => $raw_map{cs},
        cpu_us    => $raw_map{us},
        cpu_sy    => defined($raw_map{sy_2}) ? $raw_map{sy_2} : undef,
        cpu_id    => $raw_map{id},
    );

    if (!@heads || !%raw_map) {
        my $n = scalar @vals;
        $snap{r} = $vals[0] if $n > 0;
        $snap{b} = $vals[1] if $n > 1;
        $snap{w} = $vals[2] if $n > 2;
        $snap{avm} = $vals[3] if $n > 3;
        $snap{fre} = $vals[4] if $n > 4;
        $snap{pi} = $vals[7] if $n > 7;
        $snap{po} = $vals[8] if $n > 8;
        $snap{fr} = $vals[9] if $n > 9;
        $snap{sr} = $vals[10] if $n > 10;
        $snap{intr} = $vals[$n - 6] if $n >= 6;
        $snap{syscalls} = $vals[$n - 5] if $n >= 5;
        $snap{cs} = $vals[$n - 4] if $n >= 4;
        $snap{cpu_us} = $vals[$n - 3] if $n >= 3;
        $snap{cpu_sy} = $vals[$n - 2] if $n >= 2;
        $snap{cpu_id} = $vals[$n - 1] if $n >= 1;
    }
    elsif (!defined $snap{cpu_sy} && defined $snap{cpu_us} && defined $snap{cpu_id} && defined $raw_map{sy}) {
        # Some vmstat variants expose only one "sy" header; use it as CPU system%.
        $snap{cpu_sy} = $raw_map{sy};
    }

    for my $k (qw(r b w avm fre pi po fr sr intr syscalls cs cpu_us cpu_sy cpu_id)) {
        my $n = vmstat_num($snap{$k});
        $snap{$k} = defined($n) ? $n : undef;
    }
    if (defined $snap{cpu_us} && defined $snap{cpu_sy}) {
        $snap{cpu_busy} = clamp_pct($snap{cpu_us} + $snap{cpu_sy});
    }

    return \%snap;
}

sub vmstat_snapshot {
    my (%opt) = @_;
    my $wait = defined $opt{wait} ? $opt{wait} : 1;
    $wait = 1 unless defined($wait) && $wait =~ /^\d+$/;
    $wait = 1 if $wait < 1;
    $wait = 5 if $wait > 5;

    my @cmds = (
        [ '/usr/bin/vmstat', '-w', $wait, '-c', '2' ],
        [ '/usr/sbin/vmstat', '-w', $wait, '-c', '2' ],
        [ 'vmstat', '-w', $wait, '-c', '2' ],
    );

    my $last_err = '';
    for my $cmd (@cmds) {
        my $bin = $cmd->[0];
        next if $bin =~ m{^/} && !-x $bin;
        my ($rc, $out, $err) = run_cmd(@$cmd);
        if ($rc == 0 && defined($out) && $out =~ /\S/) {
            my $snap = parse_vmstat_sample($out);
            return ($snap, $out, join(' ', @$cmd), '') if $snap;
            $last_err = 'Unable to parse vmstat output';
            next;
        }
        $last_err = $err || $out || 'vmstat command failed';
    }

    return (undef, '', '', $last_err || 'vmstat command not available');
}

sub normalize_iostat_key {
    my ($k) = @_;
    return '' unless defined $k;
    $k =~ s/^\s+|\s+$//g;
    return '' if $k eq '';
    $k = lc($k);
    $k =~ s/%/pct_/g;
    $k =~ s/[^a-z0-9]+/_/g;
    $k =~ s/^_+|_+$//g;
    $k =~ s/_+/_/g;
    $k = 'pct_busy' if $k eq 'pct_b';
    return $k;
}

sub parse_iostat_rows {
    my ($out) = @_;
    return [] unless defined $out && $out =~ /\S/;

    my @lines = split /\n/, $out;
    my (@headers, @block_rows, @last_rows);

    for my $line (@lines) {
        my $ln = $line;
        $ln =~ s/\r$//;
        if ($ln =~ /^\s*$/) {
            if (@block_rows) {
                @last_rows = @block_rows;
                @block_rows = ();
            }
            next;
        }
        next if $ln =~ /^\s*(?:extended|device\s+statistics)\b/i;
        next if $ln =~ /^\s*avg-cpu:/i;
        next if $ln =~ /^\s*(?:cpu|tty)\b/i;

        if ($ln =~ /^\s*device\b/i) {
            my @h = grep { length $_ } split /\s+/, $ln;
            @headers = map { normalize_iostat_key($_) } @h;
            @block_rows = ();
            next;
        }

        next unless @headers;
        my @tok = grep { length $_ } split /\s+/, $ln;
        next unless @tok >= 2;

        my $dev = $tok[0];
        next if !defined($dev) || $dev eq '';
        next if $dev =~ /^[-+]?\d/;
        next if lc($dev) eq 'device';

        my $hstart = ($headers[0] && $headers[0] eq 'device') ? 1 : 0;
        my @vals = @tok;
        shift @vals if $hstart;
        next unless @vals;

        my %row = ( device => $dev );
        my $num_fields = 0;
        for my $i (0 .. $#vals) {
            my $hi = $i + $hstart;
            last if $hi > $#headers;
            my $hk = $headers[$hi] || '';
            next if $hk eq '' || $hk eq 'device';
            $row{$hk} = $vals[$i];
            $num_fields++ if defined($vals[$i]) && $vals[$i] =~ /^[-+]?\d+(?:\.\d+)?$/;
        }
        next unless $num_fields >= 2;
        push @block_rows, \%row;
    }

    if (@block_rows) {
        @last_rows = @block_rows;
    }
    return \@last_rows;
}

sub iostat_device_snapshot {
    my (%opt) = @_;
    my $wait = defined $opt{wait} ? $opt{wait} : 1;
    $wait = 1 unless defined($wait) && $wait =~ /^\d+$/;
    $wait = 1 if $wait < 1;
    $wait = 5 if $wait > 5;

    my @cmds = (
        [ '/usr/sbin/iostat', '-x', '-d', '-w', $wait, '-c', '2' ],
        [ '/usr/bin/iostat',  '-x', '-d', '-w', $wait, '-c', '2' ],
        [ 'iostat',           '-x', '-d', '-w', $wait, '-c', '2' ],
        [ '/usr/sbin/iostat', '-d', '-w', $wait, '-c', '2' ],
        [ '/usr/bin/iostat',  '-d', '-w', $wait, '-c', '2' ],
        [ 'iostat',           '-d', '-w', $wait, '-c', '2' ],
    );

    my $last_err = '';
    for my $cmd (@cmds) {
        my $bin = $cmd->[0];
        next if $bin =~ m{^/} && !-x $bin;
        my ($rc, $out, $err) = run_cmd(@$cmd);
        if ($rc == 0 && defined($out) && $out =~ /\S/) {
            my $rows = parse_iostat_rows($out);
            return ($rows, $out, join(' ', @$cmd), '') if $rows && @$rows;
            $last_err = 'Unable to parse iostat output';
            next;
        }
        $last_err = $err || $out || 'iostat command failed';
    }

    return ([], '', '', $last_err || 'iostat command not available');
}

sub sanitize_iostat_device_name {
    my ($dev) = @_;
    return undef unless defined $dev;
    $dev =~ s/^\s+|\s+$//g;
    return undef unless $dev =~ /^[A-Za-z0-9_.:\-]{1,32}$/;
    # CAM passthrough pseudo-devices are noisy for trend UI.
    return undef if $dev =~ /^pass\d+$/i;
    return $dev;
}

sub parse_trend_devices_param {
    my ($raw) = @_;
    my @devices;
    return \@devices unless defined $raw && $raw ne '';

    $raw =~ s/\0/,/g;
    my %seen;
    for my $tok (split /[,\s]+/, $raw) {
        my $dev = sanitize_iostat_device_name($tok);
        next unless defined $dev;
        next if $seen{$dev}++;
        push @devices, $dev;
        last if @devices >= 24;
    }
    return \@devices;
}

sub parse_busy_history_param {
    my ($raw) = @_;
    my @hist;
    return \@hist unless defined $raw && $raw ne '';

    # Hard limit prevents query-string abuse.
    $raw = substr($raw, 0, 12000);

    for my $sample (split /\|/, $raw) {
        next unless defined $sample && $sample =~ /\S/;
        my @parts = split /,/, $sample;
        next unless @parts >= 2;

        my $ts = shift @parts;
        next unless defined $ts && $ts =~ /^\d{9,11}$/;
        my %vals;
        for my $kv (@parts) {
            next unless defined $kv;
            next unless $kv =~ /^([A-Za-z0-9_.:\-]{1,32}):(-?\d+(?:\.\d+)?)$/;
            my ($dev, $busy) = ($1, $2 + 0);
            my $sdev = sanitize_iostat_device_name($dev);
            next unless defined $sdev;
            $busy = 0 if $busy < 0;
            $busy = 100 if $busy > 100;
            $vals{$sdev} = sprintf("%.1f", $busy) + 0;
        }
        next unless %vals;
        push @hist, { t => $ts + 0, v => \%vals };
        last if @hist >= 300;
    }
    return \@hist;
}

sub build_busy_history_param {
    my ($hist) = @_;
    return '' unless $hist && ref($hist) eq 'ARRAY' && @$hist;

    my @samples;
    for my $p (@$hist) {
        next unless ref($p) eq 'HASH';
        my $t = $p->{t};
        next unless defined $t && $t =~ /^\d+$/;
        my $vals = $p->{v};
        next unless ref($vals) eq 'HASH' && %$vals;

        my @pairs;
        for my $dev (sort keys %$vals) {
            my $sdev = sanitize_iostat_device_name($dev);
            next unless defined $sdev;
            my $v = vmstat_num($vals->{$dev});
            next unless defined $v;
            $v = 0 if $v < 0;
            $v = 100 if $v > 100;
            push @pairs, $sdev . ":" . sprintf("%.1f", $v);
        }
        next unless @pairs;
        push @samples, ($t . "," . join(",", @pairs));
    }

    # Keep query length bounded to avoid URL overflows/redirect oddities.
    while (@samples) {
        my $joined = join("|", @samples);
        return $joined if length($joined) <= 1800;
        shift @samples;
    }
    return '';
}

sub sanitize_livevmstat_state_id {
    my ($id) = @_;
    return undef unless defined $id;
    $id =~ s/^\s+|\s+$//g;
    return undef unless $id =~ /^[A-Za-z0-9_-]{12,64}$/;
    return $id;
}

sub generate_livevmstat_state_id {
    my $raw = sprintf("%x%x%x%x", time(), $$, int(rand(0x7fffffff)), int(rand(0x7fffffff)));
    $raw =~ s/[^A-Za-z0-9]//g;
    return substr($raw, 0, 32);
}

sub livevmstat_state_file {
    my ($state_id) = @_;
    my $sid = sanitize_livevmstat_state_id($state_id);
    return undef unless defined $sid;
    return "/tmp/livevmstat_state_" . $sid . ".txt";
}

sub livevmstat_vmcache_file {
    my ($state_id) = @_;
    my $sid = sanitize_livevmstat_state_id($state_id);
    return undef unless defined $sid;
    return "/tmp/livevmstat_vmcache_" . $sid . ".txt";
}

sub read_livevmstat_vmcache {
    my ($state_id) = @_;
    my $file = livevmstat_vmcache_file($state_id);
    return (undef, undef) unless defined $file && -f $file;
    my $data = eval { read_file_contents($file) };
    return (undef, undef) unless defined $data && length $data;
    my @lines = grep { defined $_ && $_ ne '' } split /\n/, $data;
    return (undef, undef) unless @lines;
    my $ts = shift @lines;
    $ts = undef unless defined $ts && $ts =~ /^\d+$/;
    my %vm;
    for my $ln (@lines) {
        next unless $ln =~ /^([a-z_]+)=(.*)$/;
        my ($k, $v) = ($1, $2);
        next unless $v =~ /^-?\d+(?:\.\d+)?$/;
        $vm{$k} = $v + 0;
    }
    return ($ts, \%vm);
}

sub write_livevmstat_vmcache {
    my ($state_id, $vm) = @_;
    return unless $vm && ref($vm) eq 'HASH';
    my $file = livevmstat_vmcache_file($state_id);
    return unless defined $file;
    my @keys = qw(r w b avm fre syscalls intr cs pi po fr sr cpu_busy cpu_us cpu_sy cpu_id);
    my @lines = (time());
    for my $k (@keys) {
        next unless defined $vm->{$k};
        next unless $vm->{$k} =~ /^-?\d+(?:\.\d+)?$/;
        push @lines, $k . "=" . $vm->{$k};
    }
    eval { write_file_contents($file, join("\n", @lines) . "\n") };
}

sub read_livevmstat_state {
    my ($state_id) = @_;
    my $file = livevmstat_state_file($state_id);
    return '' unless defined $file && -r $file;
    my $size = -s $file;
    return '' unless defined $size && $size > 0 && $size <= 32768;
    my $txt = '';
    if (open(my $fh, '<', $file)) {
        local $/ = undef;
        $txt = <$fh>;
        close($fh);
    }
    $txt = '' unless defined $txt;
    $txt =~ s/\s+$//;
    return $txt;
}

sub write_livevmstat_state {
    my ($state_id, $payload) = @_;
    my $file = livevmstat_state_file($state_id);
    return unless defined $file;
    $payload = '' unless defined $payload;
    $payload = substr($payload, 0, 32768);
    if (open(my $fh, '>', $file)) {
        print {$fh} $payload;
        close($fh);
        utime(time(), time(), $file);
    }
}

sub read_livevmstat_trend_devices {
    my ($state_id) = @_;
    my $sid = sanitize_livevmstat_state_id($state_id);
    return '' unless defined $sid;
    my $file = "/tmp/livevmstat_trend_" . $sid . ".txt";
    return '' unless -r $file;
    my $size = -s $file;
    return '' unless defined $size && $size > 0 && $size <= 2048;
    my $txt = '';
    if (open(my $fh, '<', $file)) {
        local $/ = undef;
        $txt = <$fh>;
        close($fh);
    }
    $txt = '' unless defined $txt;
    $txt =~ s/\s+$//;
    return $txt;
}

sub write_livevmstat_trend_devices {
    my ($state_id, $raw) = @_;
    my $sid = sanitize_livevmstat_state_id($state_id);
    return unless defined $sid;
    my $file = "/tmp/livevmstat_trend_" . $sid . ".txt";
    $raw = '' unless defined $raw;
    $raw = substr($raw, 0, 2048);
    if (open(my $fh, '>', $file)) {
        print {$fh} $raw;
        close($fh);
        utime(time(), time(), $file);
    }
}

sub build_busy_sample_from_iostat {
    my ($io_rows, $max_devices) = @_;
    $max_devices = 24 unless defined($max_devices) && $max_devices =~ /^\d+$/ && $max_devices > 0;

    my %sample;
    return \%sample unless $io_rows && ref($io_rows) eq 'ARRAY' && @$io_rows;

    my $nval = sub {
        my ($v) = @_;
        my $n = vmstat_num($v);
        return defined($n) ? $n : -1;
    };

    my @sorted = sort {
           $nval->($b->{pct_busy}) <=> $nval->($a->{pct_busy})
        || $nval->($b->{mb_s})     <=> $nval->($a->{mb_s})
        || $nval->($b->{tps})      <=> $nval->($a->{tps})
        || lc(($a->{device} // '')) cmp lc(($b->{device} // ''))
    } @$io_rows;
    splice(@sorted, $max_devices) if @sorted > $max_devices;

    for my $r (@sorted) {
        next unless ref($r) eq 'HASH';
        my $dev = sanitize_iostat_device_name($r->{device});
        next unless defined $dev;
        my $busy = vmstat_num($r->{pct_busy});
        next unless defined $busy;
        $busy = 0 if $busy < 0;
        $busy = 100 if $busy > 100;
        $sample{$dev} = sprintf("%.1f", $busy) + 0;
    }

    return \%sample;
}

sub update_busy_history {
    my (%opt) = @_;
    my $hist = $opt{history};
    my $sample = $opt{sample};
    my $window = defined($opt{window}) ? $opt{window} : 60;
    $window = 60 unless defined($window) && $window =~ /^\d+$/ && $window >= 10;

    my $now = time();
    my $min_t = $now - $window;
    my @clean;

    if ($hist && ref($hist) eq 'ARRAY') {
        for my $p (@$hist) {
            next unless ref($p) eq 'HASH';
            my $t = $p->{t};
            next unless defined $t && $t =~ /^\d+$/;
            next if $t < ($min_t - 2) || $t > ($now + 2);
            my $vals = $p->{v};
            next unless ref($vals) eq 'HASH';
            my %clean_vals;
            for my $dev (keys %$vals) {
                my $sdev = sanitize_iostat_device_name($dev);
                next unless defined $sdev;
                my $v = vmstat_num($vals->{$dev});
                next unless defined $v;
                $v = 0 if $v < 0;
                $v = 100 if $v > 100;
                $clean_vals{$sdev} = sprintf("%.1f", $v) + 0;
            }
            push @clean, { t => $t + 0, v => \%clean_vals } if %clean_vals;
        }
    }

    if ($sample && ref($sample) eq 'HASH' && %$sample) {
        my %clean_sample;
        for my $dev (keys %$sample) {
            my $sdev = sanitize_iostat_device_name($dev);
            next unless defined $sdev;
            my $v = vmstat_num($sample->{$dev});
            next unless defined $v;
            $v = 0 if $v < 0;
            $v = 100 if $v > 100;
            $clean_sample{$sdev} = sprintf("%.1f", $v) + 0;
        }
        push @clean, { t => $now, v => \%clean_sample } if %clean_sample;
    }

    @clean = sort { $a->{t} <=> $b->{t} } @clean;
    @clean = grep { $_->{t} >= $min_t } @clean;
    splice(@clean, 0, @clean - 80) if @clean > 80;
    return \@clean;
}

sub trend_devices_and_colors {
    my (%opt) = @_;
    my $hist = $opt{history};
    my $window = defined($opt{window}) ? $opt{window} : 60;
    my $device_limit = defined($opt{device_limit}) ? $opt{device_limit} : 24;
    my $selected = $opt{selected_devices};
    $window = 60 unless defined($window) && $window =~ /^\d+$/ && $window >= 10;
    $device_limit = 24 unless defined($device_limit) && $device_limit =~ /^\d+$/ && $device_limit > 0;

    my @empty = ();
    my %empty = ();
    return (\@empty, \%empty) unless $hist && ref($hist) eq 'ARRAY' && @$hist;

    my $now = time();
    my $start_t = $now - $window;
    my @pts = sort { $a->{t} <=> $b->{t} }
              grep { ref($_) eq 'HASH' && defined($_->{t}) && $_->{t} >= $start_t && $_->{t} <= ($now + 2) }
              @$hist;
    return (\@empty, \%empty) unless @pts;

    my (%max_busy, %last_busy);
    for my $p (@pts) {
        my $vals = $p->{v};
        next unless ref($vals) eq 'HASH';
        for my $dev (keys %$vals) {
            my $sdev = sanitize_iostat_device_name($dev);
            next unless defined $sdev;
            my $v = vmstat_num($vals->{$dev});
            next unless defined $v;
            $v = 0 if $v < 0;
            $v = 100 if $v > 100;
            $max_busy{$sdev} = $v if !defined($max_busy{$sdev}) || $v > $max_busy{$sdev};
            $last_busy{$sdev} = $v;
        }
    }
    return (\@empty, \%empty) unless %max_busy;

    my @devices_ranked = sort {
           $max_busy{$b} <=> $max_busy{$a}
        || $last_busy{$b} <=> $last_busy{$a}
        || lc($a) cmp lc($b)
    } keys %max_busy;

    my @devices;
    my %selected_map;
    if ($selected && ref($selected) eq 'ARRAY' && @$selected) {
        for my $d (@$selected) {
            my $sd = sanitize_iostat_device_name($d);
            next unless defined $sd;
            $selected_map{$sd} = 1;
        }
    }

    if (%selected_map) {
        @devices = grep { $selected_map{$_} } @devices_ranked;
    }
    else {
        @devices = @devices_ranked;
    }

    splice(@devices, $device_limit) if @devices > $device_limit;
    return (\@empty, \%empty) unless @devices;

    my @colors = (
        '#0d6efd', '#198754', '#fd7e14', '#dc3545', '#6f42c1', '#20c997',
        '#e83e8c', '#6610f2', '#17a2b8', '#795548', '#ff5722', '#607d8b',
        '#1f77b4', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#bcbd22',
        '#7f7f7f', '#ff1493', '#00bcd4', '#ff9800', '#4caf50', '#9c27b0'
    );
    my %dev_color;
    for my $i (0 .. $#devices) {
        $dev_color{$devices[$i]} = $colors[$i % @colors];
    }

    return (\@devices, \%dev_color);
}

sub device_color_for_name {
    my ($name) = @_;
    my @colors = (
        '#0d6efd', '#198754', '#fd7e14', '#dc3545', '#6f42c1', '#20c997',
        '#e83e8c', '#6610f2', '#17a2b8', '#795548', '#ff5722', '#607d8b',
        '#1f77b4', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#bcbd22',
        '#7f7f7f', '#ff1493', '#00bcd4', '#ff9800', '#4caf50', '#9c27b0'
    );
    return $colors[0] unless defined $name && length $name;
    my $sum = 0;
    for my $ch (split //, $name) {
        $sum += ord($ch);
    }
    return $colors[$sum % scalar(@colors)];
}

sub render_busy_trend_chart {
    my (%opt) = @_;
    my $hist = $opt{history};
    my $window = defined($opt{window}) ? $opt{window} : 60;
    my $device_limit = defined($opt{device_limit}) ? $opt{device_limit} : 24;
    my $selected = $opt{selected_devices};
    my $forced_devices = $opt{devices};
    my $forced_colors = $opt{device_colors};
    $window = 60 unless defined($window) && $window =~ /^\d+$/ && $window >= 10;
    $device_limit = 24 unless defined($device_limit) && $device_limit =~ /^\d+$/ && $device_limit > 0;

    return "<span class='zfsguru-muted'>" . &html_escape(L("VALUE_NONE")) . "</span>"
        unless $hist && ref($hist) eq 'ARRAY' && @$hist;

    my $now = time();
    my $start_t = $now - $window;
    my @pts = sort { $a->{t} <=> $b->{t} }
              grep { ref($_) eq 'HASH' && defined($_->{t}) && $_->{t} >= $start_t && $_->{t} <= ($now + 2) }
              @$hist;
    return "<span class='zfsguru-muted'>" . &html_escape(L("VALUE_NONE")) . "</span>" unless @pts;

    my (%max_busy, %last_busy);
    for my $p (@pts) {
        my $vals = $p->{v};
        next unless ref($vals) eq 'HASH';
        for my $dev (keys %$vals) {
            my $sdev = sanitize_iostat_device_name($dev);
            next unless defined $sdev;
            my $v = vmstat_num($vals->{$dev});
            next unless defined $v;
            $v = 0 if $v < 0;
            $v = 100 if $v > 100;
            $max_busy{$sdev} = $v if !defined($max_busy{$sdev}) || $v > $max_busy{$sdev};
            $last_busy{$sdev} = $v;
        }
    }
    return "<span class='zfsguru-muted'>" . &html_escape(L("VALUE_NONE")) . "</span>" unless %max_busy;

    my @devices;
    if ($forced_devices && ref($forced_devices) eq 'ARRAY' && @$forced_devices) {
        my %exists = map { $_ => 1 } keys %max_busy;
        @devices = grep { $exists{$_} } @$forced_devices;
    } else {
        my ($ranked, undef) = trend_devices_and_colors(
            history => $hist,
            window => $window,
            device_limit => $device_limit,
            selected_devices => $selected,
        );
        @devices = @$ranked if $ranked;
    }
    splice(@devices, $device_limit) if @devices > $device_limit;
    return "<span class='zfsguru-muted'>" . &html_escape(L("VALUE_NONE")) . "</span>" unless @devices;

    my %dev_color;
    if ($forced_colors && ref($forced_colors) eq 'HASH' && %$forced_colors) {
        %dev_color = %$forced_colors;
    } else {
        my ($ranked, $colors) = trend_devices_and_colors(
            history => $hist,
            window => $window,
            device_limit => $device_limit,
            selected_devices => \@devices,
        );
        %dev_color = %{$colors || {}};
    }

    my ($w, $h) = (560, 146);
    my ($m_l, $m_r, $m_t, $m_b) = (36, 10, 6, 18);
    my $plot_w = $w - $m_l - $m_r;
    my $plot_h = $h - $m_t - $m_b;
    my $range = $window > 0 ? $window : 60;

    my $x_for = sub {
        my ($t) = @_;
        my $dt = $t - $start_t;
        $dt = 0 if $dt < 0;
        $dt = $range if $dt > $range;
        return $m_l + ($dt / $range) * $plot_w;
    };
    my $y_for = sub {
        my ($v) = @_;
        $v = 0 unless defined $v;
        $v = 0 if $v < 0;
        $v = 100 if $v > 100;
        return $m_t + (1 - $v / 100) * $plot_h;
    };

    my @svg;
    push @svg, "<svg class='zfsguru-vmstat-trend-svg' viewBox='0 0 $w $h' role='img' aria-label='" .
               &html_escape(L("TABLE_LIVE_VMSTAT_BUSY_TREND", $window)) . "'>";
    push @svg, "<rect x='0' y='0' width='$w' height='$h' fill='#ffffff' />";
    push @svg, "<rect x='$m_l' y='$m_t' width='$plot_w' height='$plot_h' fill='#fbfcfe' stroke='#d7dce2' stroke-width='1' />";

    my %y_major = map { $_ => 1 } (0, 25, 50, 75, 100);
    for (my $yv = 100; $yv >= 0; $yv -= 5) {
        my $y = sprintf("%.1f", $y_for->($yv));
        my $stroke = $y_major{$yv} ? '#dde5ee' : '#eef3f8';
        my $width = $y_major{$yv} ? '0.9' : '0.6';
        push @svg, "<line x1='$m_l' y1='$y' x2='" . ($m_l + $plot_w) . "' y2='$y' stroke='$stroke' stroke-width='$width' />";
        if ($y_major{$yv}) {
            push @svg, "<text x='" . ($m_l - 3) . "' y='" . ($y + 3) . "' text-anchor='end' fill='#667788' font-size='7'>$yv%</text>";
        }
    }

    my %x_major = map { $_ => 1 } (0, int($window/4), int($window/2), int(3*$window/4), $window);
    for (my $sec = 0; $sec <= $window; $sec += 3) {
        my $x = sprintf("%.1f", $x_for->($start_t + $sec));
        my $major = $x_major{$sec} ? 1 : 0;
        my $stroke = $major ? '#dde5ee' : '#eef3f8';
        my $dash = $major ? '3 3' : '1.6 3.2';
        my $width = $major ? '0.9' : '0.6';
        push @svg, "<line x1='$x' y1='$m_t' x2='$x' y2='" . ($m_t + $plot_h) . "' stroke='$stroke' stroke-width='$width' stroke-dasharray='$dash' />";
        if ($major) {
            my $ago = $window - $sec;
            my $lbl = $ago == 0 ? L("LBL_VMSTAT_NOW") : ("-" . int($ago) . "s");
            push @svg, "<text x='$x' y='" . ($m_t + $plot_h + 12) . "' text-anchor='middle' fill='#667788' font-size='7'>" .
                       &html_escape($lbl) . "</text>";
        }
    }

    my $last_point = $pts[-1];
    my %last_vals = ref($last_point->{v}) eq 'HASH' ? %{ $last_point->{v} } : ();

    for my $dev (@devices) {
        my @coords;
        for my $p (@pts) {
            my $vals = ref($p->{v}) eq 'HASH' ? $p->{v} : {};
            my $v = exists($vals->{$dev}) ? vmstat_num($vals->{$dev}) : 0;
            $v = 0 unless defined $v;
            $v = 0 if $v < 0;
            $v = 100 if $v > 100;
            my $x = sprintf("%.1f", $x_for->($p->{t}));
            my $y = sprintf("%.1f", $y_for->($v));
            push @coords, "$x,$y";
        }
        next unless @coords;
        my $path = "M " . join(" L ", @coords);
        my $color = $dev_color{$dev} || '#0d6efd';
        push @svg, "<path d='" . &html_escape($path) . "' fill='none' stroke='$color' stroke-width='1.8' />";

        my $lv = exists($last_vals{$dev}) ? vmstat_num($last_vals{$dev}) : 0;
        $lv = 0 unless defined $lv;
        my $lx = sprintf("%.1f", $x_for->($pts[-1]->{t}));
        my $ly = sprintf("%.1f", $y_for->($lv));
        push @svg, "<circle cx='$lx' cy='$ly' r='2.8' fill='$color' />";

    }

    push @svg, "</svg>";
    return "<div class='zfsguru-vmstat-trend-wrap'>" . join("", @svg) . "</div>";
}

sub action_overview {
    print &ui_subheading(L("SUB_SYSTEM_OVERVIEW"));
    
    my $hostname = hostname();
    my ($rc, $out, $err) = run_cmd('uname', '-a');
    my $uname = $out || L("VALUE_UNKNOWN");
    
    ($rc, $out, $err) = run_cmd('uptime');
    my $uptime = $out || L("VALUE_UNKNOWN");
    
    print &ui_table_start(L("TABLE_SYSTEM_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_HOSTNAME"), $hostname);
    print &ui_table_row(L("ROW_SYSTEM"), $uname);
    print &ui_table_row(L("ROW_UPTIME"), $uptime);
    print &ui_table_end();
    
    # ZFS Information
    print &ui_subheading(L("SUB_ZFS_INFO"));
    my $zfs_ver = zfs_version();
    print &ui_table_start(L("TABLE_ZFS_DETAILS"), "width=100%", 2);
    print &ui_table_row(L("ROW_ZFS_VERSION"), $zfs_ver || L("VALUE_UNKNOWN"));
    print &ui_table_end();
    
    # Resource Summary
    print &ui_subheading(L("SUB_RESOURCE_SUMMARY"));

    my $cpu = cpu_snapshot();
    my $mem = mem_snapshot();

    my $load_text = ($cpu && $cpu->{load_text}) ? $cpu->{load_text} : L("VALUE_UNKNOWN");
    my $busy_pct = ($cpu && defined $cpu->{busy_pct}) ? $cpu->{busy_pct} : undef;

    my $mem_used_bar = L("VALUE_UNKNOWN");
    if ($mem && $mem->{total_bytes} && defined $mem->{used_pct}) {
        my $kind = ($mem->{used_pct} >= 95) ? 'bad' : ($mem->{used_pct} >= 85) ? 'warn' : 'ok';
        my $label = plain_size($mem->{used_bytes}) . " / " . plain_size($mem->{total_bytes});
        $mem_used_bar = render_bar(pct => $mem->{used_pct}, label => $label, kind => $kind);
    }

    my $cpu_busy_bar = L("VALUE_UNKNOWN");
    if (defined $busy_pct) {
        my $kind = ($busy_pct >= 95) ? 'bad' : ($busy_pct >= 85) ? 'warn' : 'ok';
        $cpu_busy_bar = render_bar(pct => $busy_pct, label => sprintf("%.1f%% busy", $busy_pct), kind => $kind);
    }

    print &ui_table_start(L("TABLE_RESOURCE_SUMMARY"), "width=100%", 2);
    print &ui_table_row(L("ROW_LOAD_AVERAGE"), &html_escape($load_text));
    print &ui_table_row(L("ROW_CPU_BUSY"), $cpu_busy_bar);
    print &ui_table_row(L("ROW_MEMORY_USED"), $mem_used_bar);
    print &ui_table_end();

    # Storage Summary
    print &ui_subheading(L("SUB_STORAGE_SUMMARY"));
    my $pools = zpool_list();
    my $datasets = zfs_list();
    my $disks = disk_list();
    
    print &ui_table_start(L("TABLE_STORAGE_OVERVIEW"), "width=100%", 2);
    print &ui_table_row(L("ROW_TOTAL_POOLS"), scalar(@$pools));
    print &ui_table_row(L("ROW_TOTAL_DATASETS"), scalar(@$datasets));
    print &ui_table_row(L("ROW_TOTAL_DISKS"), scalar(@$disks));
    print &ui_table_end();
    
    # Alert Summary
    print &ui_subheading(L("SUB_ALERT_SUMMARY"));
    
    my $alerts = 0;
    my $warnings = 0;
    
    for my $pool (@$pools) {
        my $health = defined($pool->{health}) ? $pool->{health} : '';
        my $name = $pool->{name} || '';
        if ($health ne 'ONLINE') {
            $alerts++;
        }
        if (cap_pct_value($pool->{cap}) > 80) {
            $warnings++;
        }
        my ($needs_attention, $attention_msg) = pool_needs_attention_status($name, $health);
        if ($needs_attention && $health eq 'ONLINE') {
            $warnings++;
        }
    }
    
    print &ui_table_start(L("TABLE_SYSTEM_HEALTH"), "width=100%", 2);
    print &ui_table_row(L("ROW_CRITICAL_ALERTS"), "<span class='zfsguru-status-bad'>$alerts</span>");
    print &ui_table_row(L("ROW_WARNINGS"), "<span class='zfsguru-status-warn'>$warnings</span>");
    print &ui_table_row(
        L("COL_STATUS"),
        $alerts == 0 ? "<span class='zfsguru-status-ok'>" . L("VALUE_OK") . "</span>" :
                       "<span class='zfsguru-status-bad'>" . L("VALUE_ACTION_REQUIRED") . "</span>"
    );
    print &ui_table_end();
}

sub action_cpu {
    print &ui_subheading(L("SUB_CPU_STATUS"));

    my $cpu = cpu_snapshot();
    my $model = ($cpu && $cpu->{model}) ? $cpu->{model} : L("VALUE_UNKNOWN");
    my $ncpu  = ($cpu && $cpu->{ncpu})  ? $cpu->{ncpu}  : L("VALUE_UNKNOWN");
    my $load  = ($cpu && $cpu->{load_text}) ? $cpu->{load_text} : L("VALUE_UNKNOWN");

    my $busy = defined($cpu->{busy_pct}) ? $cpu->{busy_pct} : undef;
    my $busy_bar = L("VALUE_UNKNOWN");
    if (defined $busy) {
        my $kind = ($busy >= 95) ? 'bad' : ($busy >= 85) ? 'warn' : 'ok';
        my $label = sprintf("%.1f%% busy", $busy);
        $busy_bar = render_bar(pct => $busy, label => $label, kind => $kind);
    }

    print &ui_table_start(L("TABLE_CPU_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_CPU_MODEL"), &html_escape($model));
    print &ui_table_row(L("ROW_CPU_CORES"), &html_escape($ncpu));
    print &ui_table_row(L("ROW_LOAD_AVERAGE"), &html_escape($load));
    print &ui_table_row(L("ROW_CPU_BUSY"), $busy_bar);

    if ($cpu->{cpu_pct}) {
        my $p = $cpu->{cpu_pct};
        my $user = defined($p->{user}) ? clamp_pct($p->{user}) : 0;
        my $nice = defined($p->{nice}) ? clamp_pct($p->{nice}) : 0;
        my $system = defined($p->{system}) ? clamp_pct($p->{system})
                    : defined($p->{sys})    ? clamp_pct($p->{sys})
                    : 0;
        my $intr = defined($p->{interrupt}) ? clamp_pct($p->{interrupt}) : 0;
        my $idle = defined($p->{idle}) ? clamp_pct($p->{idle}) : 0;

        my @segs = (
            { label => L("ROW_CPU_USER"), pct => $user, class => 'zfsguru-stackbar-seg-cpu-user', swatch_class => 'zfsguru-legend-swatch-cpu-user' },
        );
        push @segs, { label => L("ROW_CPU_NICE"), pct => $nice, class => 'zfsguru-stackbar-seg-cpu-nice', swatch_class => 'zfsguru-legend-swatch-cpu-nice' } if $nice > 0;
        push @segs, (
            { label => L("ROW_CPU_SYSTEM"), pct => $system, class => 'zfsguru-stackbar-seg-cpu-system', swatch_class => 'zfsguru-legend-swatch-cpu-system' },
            { label => L("ROW_CPU_INTERRUPT"), pct => $intr, class => 'zfsguru-stackbar-seg-cpu-interrupt', swatch_class => 'zfsguru-legend-swatch-cpu-interrupt' },
            { label => L("ROW_CPU_IDLE"), pct => $idle, class => 'zfsguru-stackbar-seg-cpu-idle', swatch_class => 'zfsguru-legend-swatch-cpu-idle' },
        );

        my $breakdown = render_stackbar(segments => \@segs) . render_legend(segments => \@segs);
        print &ui_table_row(L("ROW_CPU_BREAKDOWN"), $breakdown);

        print &ui_table_row(L("ROW_CPU_USER"), defined($p->{user}) ? sprintf("%.1f%%", clamp_pct($p->{user})) : '-');
        print &ui_table_row(L("ROW_CPU_NICE"), defined($p->{nice}) ? sprintf("%.1f%%", clamp_pct($p->{nice})) : '-') if defined $p->{nice};
        my $sys_disp = defined($p->{system}) ? sprintf("%.1f%%", clamp_pct($p->{system}))
                    : defined($p->{sys})    ? sprintf("%.1f%%", clamp_pct($p->{sys}))
                    : '-';
        print &ui_table_row(L("ROW_CPU_SYSTEM"), $sys_disp);
        print &ui_table_row(L("ROW_CPU_INTERRUPT"), defined($p->{interrupt}) ? sprintf("%.1f%%", clamp_pct($p->{interrupt})) : '-');
        print &ui_table_row(L("ROW_CPU_IDLE"), defined($p->{idle}) ? sprintf("%.1f%%", clamp_pct($p->{idle})) : '-');
    }

    print &ui_table_end();

    my ($rc, $ps_out, $ps_err) = run_cmd('ps', '-axo', 'pid,user,pcpu,pmem,command', '-r');
    if ($rc == 0 && $ps_out) {
        my @lines = grep { /\S/ } split /\n/, $ps_out;
        shift @lines if @lines && $lines[0] =~ /^\s*PID\s+/;
        splice(@lines, 10) if @lines > 10;

        my @heads = (L('COL_PID'), L('COL_USER'), L('COL_PCPU'), L('COL_PMEM'), L('COL_COMMAND'));
        my @data;
        for my $ln (@lines) {
            my ($pid, $user, $pcpu, $pmem, $cmd) = $ln =~ /^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+?)\s*$/;
            next unless defined $pid;
            push @data, [
                &html_escape($pid),
                &html_escape($user),
                &html_escape($pcpu),
                &html_escape($pmem),
                &html_escape($cmd),
            ];
        }

        print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_TOP_CPU"), L("VALUE_UNKNOWN"));
    } else {
        print &ui_print_error(L("ERR_PS_FAILED"));
    }
}

sub action_memory {
    print &ui_subheading(L("SUB_MEMORY_STATUS"));

    my $mem = mem_snapshot();
    if (!$mem) {
        print &ui_print_error(L("ERR_MEMINFO_FAILED"));
        return;
    }

    my $used_kind = ($mem->{used_pct} >= 95) ? 'bad' : ($mem->{used_pct} >= 85) ? 'warn' : 'ok';
    my $used_label = plain_size($mem->{used_bytes}) . " / " . plain_size($mem->{total_bytes});

    print &ui_table_start(L("TABLE_MEMORY_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_MEMORY_TOTAL"), &html_escape(plain_size($mem->{total_bytes})));
    print &ui_table_row(L("ROW_MEMORY_FREE"), &html_escape(defined($mem->{free_bytes}) ? plain_size($mem->{free_bytes}) : L("VALUE_UNKNOWN")));
    print &ui_table_row(L("ROW_MEMORY_USED"), render_bar(pct => $mem->{used_pct}, label => $used_label, kind => $used_kind));

    if ($mem->{total_bytes} && $mem->{total_bytes} > 0) {
        my $t = $mem->{total_bytes};
        my $wired = defined $mem->{wired_bytes} ? $mem->{wired_bytes} : 0;
        my $active = defined $mem->{active_bytes} ? $mem->{active_bytes} : 0;
        my $inactive = defined $mem->{inactive_bytes} ? $mem->{inactive_bytes} : 0;
        my $cache = defined $mem->{cache_bytes} ? $mem->{cache_bytes} : 0;
        my $laundry = defined $mem->{laundry_bytes} ? $mem->{laundry_bytes} : 0;
        my $free = defined $mem->{free_bytes} ? $mem->{free_bytes} : 0;

        my $sum = $wired + $active + $inactive + $cache + $laundry + $free;
        my $other = $t - $sum;
        $other = 0 if $other < 0;

        my $pct = sub {
            my ($b) = @_;
            $b = 0 unless defined $b && $b =~ /^\d+(?:\.\d+)?$/;
            return ($t > 0) ? (($b / $t) * 100) : 0;
        };

        my @segs = (
            { label => L("ROW_MEMORY_WIRED"), pct => $pct->($wired), class => 'zfsguru-stackbar-seg-mem-wired', swatch_class => 'zfsguru-legend-swatch-mem-wired' },
            { label => L("ROW_MEMORY_ACTIVE"), pct => $pct->($active), class => 'zfsguru-stackbar-seg-mem-active', swatch_class => 'zfsguru-legend-swatch-mem-active' },
            { label => L("ROW_MEMORY_INACTIVE"), pct => $pct->($inactive), class => 'zfsguru-stackbar-seg-mem-inactive', swatch_class => 'zfsguru-legend-swatch-mem-inactive' },
            { label => L("ROW_MEMORY_CACHE"), pct => $pct->($cache), class => 'zfsguru-stackbar-seg-mem-cache', swatch_class => 'zfsguru-legend-swatch-mem-cache' },
        );
        push @segs, { label => L("ROW_MEMORY_LAUNDRY"), pct => $pct->($laundry), class => 'zfsguru-stackbar-seg-mem-laundry', swatch_class => 'zfsguru-legend-swatch-mem-laundry' } if $laundry > 0;
        push @segs, { label => L("ROW_MEMORY_OTHER"), pct => $pct->($other), class => 'zfsguru-stackbar-seg-mem-other', swatch_class => 'zfsguru-legend-swatch-mem-other' } if $other > 0;
        push @segs, { label => L("ROW_MEMORY_FREE"), pct => $pct->($free), class => 'zfsguru-stackbar-seg-mem-free', swatch_class => 'zfsguru-legend-swatch-mem-free' };

        my $breakdown = render_stackbar(segments => \@segs) . render_legend(segments => \@segs);
        print &ui_table_row(L("ROW_MEMORY_BREAKDOWN"), $breakdown);
    }

    for my $row (
        [ 'ROW_MEMORY_ACTIVE',   $mem->{active_bytes}   ],
        [ 'ROW_MEMORY_INACTIVE', $mem->{inactive_bytes} ],
        [ 'ROW_MEMORY_CACHE',    $mem->{cache_bytes}    ],
        [ 'ROW_MEMORY_WIRED',    $mem->{wired_bytes}    ],
    ) {
        my ($k, $b) = @$row;
        next unless defined $b;
        print &ui_table_row(L($k), &html_escape(plain_size($b)));
    }

    if (defined $mem->{swap_total_bytes}) {
        if (($mem->{swap_total_bytes} || 0) > 0) {
            my $swap_kind = ($mem->{swap_used_pct} >= 95) ? 'bad' : ($mem->{swap_used_pct} >= 85) ? 'warn' : 'ok';
            my $swap_label = plain_size($mem->{swap_used_bytes}) . " / " . plain_size($mem->{swap_total_bytes});
            print &ui_table_row(L("ROW_SWAP_USED"), render_bar(pct => $mem->{swap_used_pct}, label => $swap_label, kind => $swap_kind));
        } else {
            print &ui_table_row(L("ROW_SWAP_USED"), "0 / 0 (no swap configured)");
        }
    } else {
        print &ui_table_row(L("ROW_SWAP_USED"), L("VALUE_UNKNOWN"));
    }

    print &ui_table_end();

    my ($rc, $ps_out, $ps_err) = run_cmd('ps', '-axo', 'pid,user,pmem,rss,vsz,command', '-m');
    if ($rc == 0 && $ps_out) {
        my @lines = grep { /\S/ } split /\n/, $ps_out;
        shift @lines if @lines && $lines[0] =~ /^\s*PID\s+/;
        splice(@lines, 10) if @lines > 10;

        my @heads = (L('COL_PID'), L('COL_USER'), L('COL_PMEM'), L('COL_RSS'), L('COL_VSZ'), L('COL_COMMAND'));
        my @data;
        for my $ln (@lines) {
            my ($pid, $user, $pmem, $rss, $vsz, $cmd) = $ln =~ /^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+?)\s*$/;
            next unless defined $pid;
            push @data, [
                &html_escape($pid),
                &html_escape($user),
                &html_escape($pmem),
                &html_escape($rss),
                &html_escape($vsz),
                &html_escape($cmd),
            ];
        }

        print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_TOP_MEMORY"), L("VALUE_UNKNOWN"));
    } else {
        print &ui_print_error(L("ERR_PS_FAILED"));
    }
}

sub action_live_vmstat {
    my ($partial_only) = @_;
    $partial_only = $partial_only ? 1 : 0;
    print &ui_subheading(L("SUB_LIVE_VMSTAT")) unless $partial_only;

    my $interval = defined($in{'interval'}) ? $in{'interval'} : 10;
    $interval =~ s/^\s+|\s+$//g;
    $interval = 10 unless $interval =~ /^\d+$/;
    $interval = 1 if $interval < 1;
    $interval = 30 if $interval > 30;
    my $window_sec = defined($in{'trend_window'}) ? $in{'trend_window'} : 120;
    $window_sec =~ s/^\s+|\s+$//g;
    $window_sec = 120 unless $window_sec =~ /^\d+$/;
    $window_sec = 15 if $window_sec < 15;
    $window_sec = 600 if $window_sec > 600;
    my $auto = (defined($in{'autorefresh'}) && $in{'autorefresh'} eq '1') ? 1 : 0;
    $auto = 0 if $partial_only;
    $interval = 5 if $auto && $interval < 5;
    my $state_id = sanitize_livevmstat_state_id($in{'state_id'});
    $state_id = generate_livevmstat_state_id() unless defined $state_id;
    my $hist_in = '';
    if (defined $in{'busy_hist'} && $in{'busy_hist'} ne '') {
        # Backward-compatible fallback for older URLs.
        $hist_in = $in{'busy_hist'};
    } else {
        $hist_in = read_livevmstat_state($state_id);
    }
    my $busy_hist = parse_busy_history_param($hist_in);

    my $xv = 1;
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $xv = $in{'xnavigation'};
    }
    my $xnav_q = "&xnavigation=$xv";
    my $xnav_h = &ui_hidden("xnavigation", $xv);

    my $refresh_mode = defined($in{'refresh_mode'}) ? $in{'refresh_mode'} : '';
    my $is_auto_tick = ($auto && $refresh_mode eq 'refresh_auto') ? 1 : 0;
    my $sample_min_interval = 12;
    my $trend_device_limit = 24;

    my $latest_hist_t = 0;
    if ($busy_hist && ref($busy_hist) eq 'ARRAY') {
        for my $p (@$busy_hist) {
            next unless ref($p) eq 'HASH' && defined($p->{t}) && $p->{t} =~ /^\d+$/;
            $latest_hist_t = $p->{t} if $p->{t} > $latest_hist_t;
        }
    }
    my ($vm_cache_t, $vm_cache) = read_livevmstat_vmcache($state_id);
    my $now_t = time();
    my $can_reuse_cache = $is_auto_tick
        && $vm_cache && ref($vm_cache) eq 'HASH'
        && $vm_cache_t && ($now_t - $vm_cache_t) < $sample_min_interval
        && $latest_hist_t && ($now_t - $latest_hist_t) < $sample_min_interval;

    my ($vm, $raw_out, $cmd_txt, $vm_err) = (undef, '', '', '');
    my ($io_rows, $io_raw, $io_cmd, $io_err) = ([], '', '', '');
    if ($can_reuse_cache) {
        $vm = $vm_cache;
    } else {
        ($vm, $raw_out, $cmd_txt, $vm_err) = vmstat_snapshot(wait => 1);
        if (!$vm) {
            print &ui_print_error(L("ERR_VMSTAT_FAILED", $vm_err || L("VALUE_UNKNOWN")));
            return;
        }
        write_livevmstat_vmcache($state_id, $vm);

        ($io_rows, $io_raw, $io_cmd, $io_err) = iostat_device_snapshot(wait => 1);
        my $busy_sample = build_busy_sample_from_iostat($io_rows, $trend_device_limit);
        $busy_hist = update_busy_history(
            history => $busy_hist,
            sample  => $busy_sample,
            window  => $window_sec,
        );
    }
    my $hist_out = build_busy_history_param($busy_hist);
    write_livevmstat_state($state_id, $hist_out);
    my $state_q = "&state_id=" . &url_encode($state_id);

    my $nval = sub {
        my ($v) = @_;
        return 0 unless defined $v;
        $v =~ s/^\s+|\s+$//g;
        return 0 unless $v =~ /^-?\d+(?:\.\d+)?$/;
        return $v + 0;
    };

    my @io_sorted_for_picks = ();
    if ($io_rows && ref($io_rows) eq 'ARRAY') {
        @io_sorted_for_picks = sort {
               $nval->($b->{pct_busy}) <=> $nval->($a->{pct_busy})
            || $nval->($b->{mb_s})     <=> $nval->($a->{mb_s})
            || $nval->($b->{tps})      <=> $nval->($a->{tps})
            || lc(($a->{device} // '')) cmp lc(($b->{device} // ''))
        } @$io_rows;
    }

    my $trend_raw = defined($in{'trend_devices'}) ? $in{'trend_devices'} : '';
    if (!defined($trend_raw) || $trend_raw eq '') {
        $trend_raw = read_livevmstat_trend_devices($state_id);
    }
    my $trend_devices = parse_trend_devices_param($trend_raw);
    my $has_device_flags = 0;
    my @trend_from_flags;
    my %flag_seen;
    for my $k (keys %in) {
        next unless defined $k;
        next unless $k =~ /^trend_dev_(.+)$/;
        my $dev = sanitize_iostat_device_name($1);
        next unless defined $dev;
        $has_device_flags = 1;
        next unless defined($in{$k}) && $in{$k} ne '' && $in{$k} ne '0';
        next if $flag_seen{$dev}++;
        push @trend_from_flags, $dev;
    }
    if ($has_device_flags) {
        $trend_devices = \@trend_from_flags;
    }

    my @available_devices;
    my %dev_seen;
    for my $dev (@$trend_devices) {
        my $sdev = sanitize_iostat_device_name($dev);
        next unless defined $sdev;
        next if $dev_seen{$sdev}++;
        push @available_devices, $sdev;
        last if @available_devices >= $trend_device_limit;
    }
    for my $r (@io_sorted_for_picks) {
        next unless ref($r) eq 'HASH';
        my $dev = sanitize_iostat_device_name($r->{device});
        next unless defined $dev;
        next if $dev_seen{$dev}++;
        push @available_devices, $dev;
        last if @available_devices >= $trend_device_limit;
    }
    if (!@$trend_devices && @available_devices && !$has_device_flags) {
        @$trend_devices = @available_devices[0 .. ($#available_devices < 3 ? $#available_devices : 3)];
    }
    write_livevmstat_trend_devices($state_id, join(",", @$trend_devices));

    my ($trend_render_devices, $trend_color_map) = ([], {});
    if (!($has_device_flags && !@$trend_devices)) {
        ($trend_render_devices, $trend_color_map) = trend_devices_and_colors(
            history => $busy_hist,
            window => $window_sec,
            device_limit => $trend_device_limit,
            selected_devices => $trend_devices,
        );
    }

    my %latest_busy_by_device;
    if ($io_rows && ref($io_rows) eq 'ARRAY') {
        for my $r (@$io_rows) {
            next unless ref($r) eq 'HASH';
            my $dev = sanitize_iostat_device_name($r->{device});
            next unless defined $dev;
            my $v = vmstat_num($r->{pct_busy});
            next unless defined $v;
            $v = 0 if $v < 0;
            $v = 100 if $v > 100;
            $latest_busy_by_device{$dev} = $v;
        }
    }
    if (!%latest_busy_by_device && $busy_hist && ref($busy_hist) eq 'ARRAY' && @$busy_hist) {
        my @hist_sorted = sort { ($a->{t} || 0) <=> ($b->{t} || 0) }
                          grep { ref($_) eq 'HASH' && defined($_->{t}) } @$busy_hist;
        if (@hist_sorted) {
            my $last_vals = $hist_sorted[-1]->{v};
            if (ref($last_vals) eq 'HASH') {
                for my $dev (keys %$last_vals) {
                    my $sdev = sanitize_iostat_device_name($dev);
                    next unless defined $sdev;
                    my $v = vmstat_num($last_vals->{$dev});
                    next unless defined $v;
                    $v = 0 if $v < 0;
                    $v = 100 if $v > 100;
                    $latest_busy_by_device{$sdev} = $v;
                }
            }
        }
    }

    my $trend_q = '';

    my $self_script = $status_script;
    my $proto = ($ENV{'HTTPS'} && $ENV{'HTTPS'} !~ /^(?:0|off)$/i) ? 'https' : 'http';
    my $host = $ENV{'HTTP_HOST'} || $ENV{'SERVER_NAME'} || '';
    my $self_abs = $host ? ($proto . "://" . $host . $self_script) : $self_script;
    my $base_common = $self_abs . "?action=live_vmstat&interval=$interval$state_q$trend_q";
    my $refresh_link = $base_common . "&autorefresh=1$xnav_q";

    my @interval_opts = map { [ $_, $_ . "s" ] } (1, 2, 3, 5, 10, 15, 30);
    print "<div class='zfsguru-livevmstat-panel'>";
    print &ui_form_start($self_abs, "get");
    print &ui_hidden("action", "live_vmstat");
    print &ui_hidden("livevmstat_form_marker", "1");
    print &ui_hidden("state_id", $state_id);
    print &ui_hidden("trend_devices", join(",", @$trend_devices));
    print &ui_hidden("autorefresh", $auto ? "1" : "0");
    print &ui_hidden("refresh_mode", "");
    print $xnav_h if $xnav_h;
    # Keep Apply URL short/stable; busy history is carried by refresh links.

    print "<div class='zfsguru-livevmstat-controls'>";
    print "<label class='zfsguru-livevmstat-label'>" . &html_escape(L("ROW_AUTO_REFRESH_INTERVAL")) . "</label>";
    print "<span class='zfsguru-livevmstat-field'>" . &ui_select("interval", $interval, \@interval_opts) . "</span>";
    my @window_opts = (
        [ 30,  "30s" ],
        [ 60,  "60s" ],
        [ 120, "120s" ],
        [ 300, "300s" ],
        [ 600, "600s" ],
    );
    print "<label class='zfsguru-livevmstat-label'>" . &html_escape(L("ROW_VMSTAT_TREND_WINDOW")) . "</label>";
    print "<span class='zfsguru-livevmstat-field'>" . &ui_select("trend_window", $window_sec, \@window_opts) . "</span>";
    print "<span class='zfsguru-livevmstat-label'>" . &html_escape(L("ROW_AUTO_REFRESH")) . ":</span>";
    print "<span class='zfsguru-livevmstat-field'>" .
          ($auto
            ? "<span class='zfsguru-status-ok'>" . &html_escape(L("OPT_YES")) . "</span>"
            : "<span class='zfsguru-status-unknown'>" . &html_escape(L("OPT_NO")) . "</span>") .
          "</span>";
    print "<span class='zfsguru-livevmstat-actions-buttons'>";
    print "<button type='button' class='ui_button' onclick=\"return zfsguruVmstatSubmit('refresh');\">" . &html_escape(L("BTN_REFRESH")) . "</button>";
    if ($auto) {
        print " <button type='button' class='ui_button ui_link_danger' onclick=\"return zfsguruVmstatSubmit('stop');\">" . &html_escape(L("BTN_STOP_REFRESH")) . "</button>";
    } else {
        print " <button type='button' class='ui_button' onclick=\"return zfsguruVmstatSubmit('start');\">" . &html_escape(L("BTN_START_REFRESH")) . "</button>";
    }
    print "</span>";
    print "</div>";

    if (@available_devices) {
        print "<div class='zfsguru-livevmstat-controls'>";
        print "<span class='zfsguru-livevmstat-label'>" . &html_escape(L("ROW_VMSTAT_TREND_DEVICES")) . "</span>";
        print "<span class='zfsguru-livevmstat-quick'>";
        print "<button type='button' class='ui_button zfsguru-livevmstat-mini-btn' ".
              "onclick=\"window.__zfsguruVmstatInteract=1; if(window.__zfsguruVmstatTimer){clearTimeout(window.__zfsguruVmstatTimer);} var c=this.form.querySelectorAll('.zfsguru-trend-dev-cb'); for(var i=0;i<c.length;i++){c[i].checked=true;} if(window.zfsguruSyncTrend){window.zfsguruSyncTrend(this.form);} return false;\">" .
              &html_escape(L("BTN_SELECT_ALL")) . "</button>";
        print "<button type='button' class='ui_button zfsguru-livevmstat-mini-btn' ".
              "onclick=\"window.__zfsguruVmstatInteract=1; if(window.__zfsguruVmstatTimer){clearTimeout(window.__zfsguruVmstatTimer);} var c=this.form.querySelectorAll('.zfsguru-trend-dev-cb'); for(var i=0;i<c.length;i++){c[i].checked=false;} if(window.zfsguruSyncTrend){window.zfsguruSyncTrend(this.form);} return false;\">" .
              &html_escape(L("BTN_CLEAR")) . "</button>";
        print "</span>";
        print "<span class='zfsguru-livevmstat-device-list'>";
        my %selected_map = map { $_ => 1 } @$trend_devices;
        for my $dev (@available_devices) {
            my $checked = $selected_map{$dev} ? " checked='checked'" : '';
            my $c = ($trend_color_map && ref($trend_color_map) eq 'HASH' && $trend_color_map->{$dev}) ? $trend_color_map->{$dev} : device_color_for_name($dev);
            my $busy_now = exists($latest_busy_by_device{$dev}) ? sprintf("%.1f%%", $latest_busy_by_device{$dev}) : '--';
            my $dev_key = "trend_dev_" . $dev;
            print "<label class='zfsguru-livevmstat-device-item' style='--trend-color:" . &html_escape($c) . "; display:inline-flex; flex-direction:column; align-items:stretch; gap:2px; min-width:60px; padding:3px 5px 4px 5px; border:1px solid #d7dce2; border-radius:4px; background:#fff; vertical-align:top;'>" .
                  "<span class='zfsguru-livevmstat-device-head' style='display:block;'>" .
                  "<span class='zfsguru-livevmstat-device-busy' style='display:block; text-align:center; font-size:10px; line-height:1.1; font-weight:700; color:" . &html_escape($c) . ";'>" . &html_escape($busy_now) . "</span>" .
                  "<span class='zfsguru-livevmstat-device-stripe' style='display:block; height:3px; border-radius:2px; margin-top:1px; background:" . &html_escape($c) . ";'></span>" .
                  "</span>" .
                  "<span class='zfsguru-livevmstat-device-main' style='display:inline-flex; align-items:center; justify-content:center; gap:4px; font-size:11px; font-weight:600; color:#2b3947; white-space:nowrap;'>" .
                  "<input class='zfsguru-trend-dev-cb' style='margin:0;' type='checkbox' name='" . &html_escape($dev_key) . "' value='1'$checked>" .
                  "<span class='zfsguru-livevmstat-device-name' style='display:inline-block; color:" . &html_escape($c) . ";'>" . &html_escape($dev) . "</span>" .
                  "</span>" .
                  "</label>";
        }
        print "</span>";
        print "<button type='submit' class='ui_button' onclick=\"if(window.zfsguruSyncTrend){window.zfsguruSyncTrend(this.form);} \">" . &html_escape(L("BTN_APPLY")) . "</button>";
        print "</div>";
    } else {
        print "<div class='zfsguru-livevmstat-controls'>";
        print "<button type='submit' class='ui_button' onclick=\"if(window.zfsguruSyncTrend){window.zfsguruSyncTrend(this.form);} \">" . &html_escape(L("BTN_APPLY")) . "</button>";
        print "</div>";
    }

    print &ui_form_end();
    print "<script>(function(){var h=document.querySelector(\"form input[name='livevmstat_form_marker'][value='1']\"); if(!h||!h.form){return;} var f=h.form; window.zfsguruSyncTrend=function(frm){ if(!frm){return;} var out=[]; var c=frm.querySelectorAll('.zfsguru-trend-dev-cb'); for(var i=0;i<c.length;i++){ if(c[i].checked){ var n=(c[i].name||''); if(n.indexOf('trend_dev_')===0){ out.push(n.substring(10)); } } } var hdev=frm.querySelector(\"input[name='trend_devices']\"); if(hdev){ hdev.value=out.join(','); } }; window.zfsguruVmstatSubmit=function(mode){ if(window.__zfsguruVmstatTimer){ clearTimeout(window.__zfsguruVmstatTimer); window.__zfsguruVmstatTimer=null; } var af=f.querySelector(\"input[name='autorefresh']\"); if(af && (mode==='start' || mode==='stop')){ af.value=(mode==='start'?'1':'0'); } var rm=f.querySelector(\"input[name='refresh_mode']\"); if(rm){ rm.value=(mode||''); } window.zfsguruSyncTrend(f); f.submit(); return false; }; f.addEventListener('submit',function(){ var rm=f.querySelector(\"input[name='refresh_mode']\"); if(rm && !rm.value){ rm.value='apply'; } window.zfsguruSyncTrend(f); }); var autoOn=" . ($auto ? "1" : "0") . "; var autoMs=" . int($interval * 1000) . "; if(autoOn==1 && autoMs>=1000){ window.__zfsguruVmstatTimer=setTimeout(function(){ window.zfsguruVmstatSubmit('refresh_auto'); }, autoMs); }})();</script>";
    print "</div>";

    my $sample_time = scalar localtime();

    my $cpu_busy_bar = L("VALUE_UNKNOWN");
    if (defined $vm->{cpu_busy}) {
        my $kind = ($vm->{cpu_busy} >= 95) ? 'bad' : ($vm->{cpu_busy} >= 85) ? 'warn' : 'ok';
        $cpu_busy_bar = render_bar(
            pct   => $vm->{cpu_busy},
            label => sprintf("%.1f%% busy", $vm->{cpu_busy}),
            kind  => $kind
        );
    }

    my $cpu_breakdown = L("VALUE_UNKNOWN");
    if (defined $vm->{cpu_us} && defined $vm->{cpu_sy} && defined $vm->{cpu_id}) {
        my @segs = (
            { label => L("ROW_CPU_USER"),   pct => clamp_pct($vm->{cpu_us}), class => 'zfsguru-stackbar-seg-cpu-user',   swatch_class => 'zfsguru-legend-swatch-cpu-user' },
            { label => L("ROW_CPU_SYSTEM"), pct => clamp_pct($vm->{cpu_sy}), class => 'zfsguru-stackbar-seg-cpu-system', swatch_class => 'zfsguru-legend-swatch-cpu-system' },
            { label => L("ROW_CPU_IDLE"),   pct => clamp_pct($vm->{cpu_id}), class => 'zfsguru-stackbar-seg-cpu-idle',   swatch_class => 'zfsguru-legend-swatch-cpu-idle' },
        );
        $cpu_breakdown = render_stackbar(segments => \@segs) . render_legend(segments => \@segs);
    }

    print &ui_table_start(L("TABLE_LIVE_VMSTAT_CPU"), "width=100%", 2);
    print &ui_table_row(L("ROW_VMSTAT_SAMPLE_TIME"), &html_escape($sample_time));
    print &ui_table_row(L("ROW_CPU_BUSY"), $cpu_busy_bar);
    print &ui_table_row(L("ROW_CPU_BREAKDOWN"), $cpu_breakdown);
    print &ui_table_end();

    my $fmt = sub {
        my ($v) = @_;
        return '-' unless defined $v;
        return &html_escape($v);
    };
    my @heads = (L("COL_METRIC"), L("COL_VALUE"), L("COL_METRIC"), L("COL_VALUE"));
    my @rows = (
        [ L("ROW_VMSTAT_RUNQ"),       $fmt->($vm->{r}),        L("ROW_VMSTAT_BLOCKED"),    $fmt->($vm->{b}) ],
        [ L("ROW_VMSTAT_SWAPPED"),    $fmt->($vm->{w}),        L("ROW_VMSTAT_AVM"),        $fmt->($vm->{avm}) ],
        [ L("ROW_VMSTAT_FRE"),        $fmt->($vm->{fre}),      L("ROW_VMSTAT_INTERRUPTS"), $fmt->($vm->{intr}) ],
        [ L("ROW_VMSTAT_SYSCALLS"),   $fmt->($vm->{syscalls}), L("ROW_VMSTAT_CTX_SWITCH"), $fmt->($vm->{cs}) ],
        [ L("ROW_VMSTAT_PAGEIN"),     $fmt->($vm->{pi}),       L("ROW_VMSTAT_PAGEOUT"),    $fmt->($vm->{po}) ],
        [ L("ROW_VMSTAT_PAGES_FREED"),$fmt->($vm->{fr}),       L("ROW_VMSTAT_PAGE_SCAN"),  $fmt->($vm->{sr}) ],
    );
    my $snapshot_html = &ui_columns_table(\@heads, 100, \@rows, undef, 1, L("TABLE_LIVE_VMSTAT_SNAPSHOT"), L("VALUE_NONE"));
    my $trend_html = '';
    if ($has_device_flags && !@$trend_devices) {
        $trend_html .= "<h3 class='zfsguru-livevmstat-cardtitle'>" . &html_escape(L("TABLE_LIVE_VMSTAT_BUSY_TREND", $window_sec)) . "</h3>";
        $trend_html .= "<p class='zfsguru-muted'>" . &html_escape(L("MSG_LIVE_VMSTAT_NO_TREND_DEVICES")) . "</p>";
    }
    elsif ($busy_hist && ref($busy_hist) eq 'ARRAY' && @$busy_hist) {
        $trend_html .= "<h3 class='zfsguru-livevmstat-cardtitle'>" . &html_escape(L("TABLE_LIVE_VMSTAT_BUSY_TREND", $window_sec)) . "</h3>";
        $trend_html .= "<p class='zfsguru-muted'>" . &html_escape(L("MSG_LIVE_VMSTAT_BUSY_TREND_NOTE")) . "</p>";
        $trend_html .= render_busy_trend_chart(
            history      => $busy_hist,
            window       => $window_sec,
            device_limit => $trend_device_limit,
            selected_devices => $trend_devices,
            devices => $trend_render_devices,
            device_colors => $trend_color_map,
        );
    } elsif ($io_err) {
        $trend_html .= &ui_alert(L("WARN_LIVE_VMSTAT_IOSTAT_UNAVAILABLE", $io_err), 'warning');
    } else {
        $trend_html .= "<span class='zfsguru-muted'>" . &html_escape(L("VALUE_NONE")) . "</span>";
    }

    print "<div class='zfsguru-livevmstat-main-grid'>";
    print "<div class='zfsguru-livevmstat-main-col'>$snapshot_html</div>";
    print "<div class='zfsguru-livevmstat-main-col'>$trend_html</div>";
    print "</div>";

    # Raw iostat/vmstat output blocks intentionally hidden for cleaner dashboard UI.
}

sub action_hardware {
    print &ui_subheading(L("SUB_HARDWARE_INFO"));

    my $osrelease = sysctl_val('kern.osrelease') || L("VALUE_UNKNOWN");
    my $ostype    = sysctl_val('kern.ostype') || L("VALUE_UNKNOWN");
    my $version   = sysctl_val('kern.version') || L("VALUE_UNKNOWN");
    my $machine   = sysctl_val('hw.machine') || L("VALUE_UNKNOWN");
    my $arch      = sysctl_val('hw.machine_arch') || L("VALUE_UNKNOWN");

    my $cpu = cpu_snapshot();
    my $mem = mem_snapshot();

    print &ui_table_start(L("TABLE_HARDWARE_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_OS"), &html_escape("$ostype $osrelease"));
    print &ui_table_row(L("ROW_KERNEL"), "<pre class='zfsguru-code-block'>" . &html_escape($version) . "</pre>");
    print &ui_table_row(L("ROW_MACHINE"), &html_escape("$machine / $arch"));
    if ($cpu && $cpu->{model}) {
        print &ui_table_row(L("ROW_CPU_MODEL"), &html_escape($cpu->{model}));
    }
    if ($cpu && $cpu->{ncpu}) {
        print &ui_table_row(L("ROW_CPU_CORES"), &html_escape($cpu->{ncpu}));
    }
    if ($mem && $mem->{total_bytes}) {
        print &ui_table_row(L("ROW_MEMORY_TOTAL"), &html_escape(plain_size($mem->{total_bytes})));
    }
    print &ui_table_end();

    my $cam = $zfsguru_lib::CAMCONTROL || 'camcontrol';
    my ($rc, $out, $err) = run_cmd($cam, 'devlist');
    if ($rc == 0 && $out) {
        print &ui_subheading(L("SUB_STORAGE_DEVICES"));
        print "<pre class='zfsguru-code-block'>" . &html_escape($out) . "</pre>";
    }

    # PCI/PCIe inventory (includes storage/network/graphics controllers on FreeBSD).
    my $pciconf = '/usr/sbin/pciconf';
    if (-x $pciconf) {
        my ($prc, $pout, $perr) = run_cmd($pciconf, '-lv');
        if ($prc == 0 && $pout) {
            my (@storage, @network, @graphics, @usb, @other);
            my @blocks = split(/\n\n+/, $pout);
            for my $b (@blocks) {
                next unless $b =~ /\S/;
                my $first = (split(/\n/, $b))[0] || '';
                my $entry = $first;
                if ($b =~ /class=0x01/i) {
                    push @storage, $entry;
                } elsif ($b =~ /class=0x02/i) {
                    push @network, $entry;
                } elsif ($b =~ /class=0x03/i) {
                    push @graphics, $entry;
                } elsif ($b =~ /class=0x0c03/i) {
                    push @usb, $entry;
                } else {
                    push @other, $entry;
                }
            }

            print &ui_subheading("PCI / PCIe Summary");
            print &ui_table_start("PCI / PCIe Summary", "width=100%", 2);
            print &ui_table_row("Storage Controllers", @storage ? "<pre class='zfsguru-code-block'>" . &html_escape(join("\n", @storage)) . "</pre>" : L("VALUE_NONE"));
            print &ui_table_row("Network Controllers", @network ? "<pre class='zfsguru-code-block'>" . &html_escape(join("\n", @network)) . "</pre>" : L("VALUE_NONE"));
            print &ui_table_row("Graphics Controllers", @graphics ? "<pre class='zfsguru-code-block'>" . &html_escape(join("\n", @graphics)) . "</pre>" : L("VALUE_NONE"));
            print &ui_table_row("USB Controllers", @usb ? "<pre class='zfsguru-code-block'>" . &html_escape(join("\n", @usb)) . "</pre>" : L("VALUE_NONE"));
            print &ui_table_end();

            print &ui_subheading("PCI / PCIe Devices");
            print "<pre class='zfsguru-code-block'>" . &html_escape($pout) . "</pre>";
        }
    }

    # USB inventory.
    my $usbconfig = '/usr/sbin/usbconfig';
    if (-x $usbconfig) {
        my ($urc, $uout, $uerr) = run_cmd($usbconfig);
        if ($urc == 0 && $uout) {
            print &ui_subheading("USB Devices");
            print "<pre class='zfsguru-code-block'>" . &html_escape($uout) . "</pre>";
        }
    }
}

sub action_pools {
    print &ui_subheading(L("SUB_POOL_STATUS_REPORT"));
    
    my $pools = zpool_list();
    
    my @heads = (L("COL_POOL"), L("COL_SIZE"), L("COL_ALLOCATED"), L("COL_FREE"), L("COL_CAPACITY"), L("COL_STATUS"));
    my @data;
    for my $pool (@$pools) {
        my $pool_name = $pool->{name};
        my $pool_link = '<a class="zfsguru-link" href="advanced_pools.cgi?action=view&pool=' . &url_encode($pool_name) . '">' . $pool_name . '</a>';
        my $health = defined $pool->{health} ? $pool->{health} : '';
        my ($needs_attention, $attention_msg) = pool_needs_attention_status($pool_name, $health);
        my ($status_class, $status_display);
        if ($needs_attention && $health eq 'ONLINE') {
            $status_class = 'zfsguru-status-warn';
            my $safe_msg = &html_escape($attention_msg || '');
            my $title_attr = $safe_msg ne '' ? " title='$safe_msg'" : '';
            $status_display = "<span class='$status_class zfsguru-status-badge'$title_attr>" .
                              &html_escape($health) .
                              "<br><span class='zfsguru-status-note'>Action required!</span></span>";
        } else {
            $status_class = $health eq 'ONLINE' ? 'zfsguru-status-ok' : ($health ? 'zfsguru-status-bad' : 'zfsguru-status-unknown');
            $status_display = "<span class='$status_class'>" . &html_escape($health || L("VALUE_UNKNOWN")) . "</span>";
        }
        
        push @data, [
            $pool_link,
            $pool->{size},
            $pool->{alloc},
            $pool->{free},
            $pool->{cap},
            $status_display
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_POOL_DETAILS"), L("ERR_NO_POOLS_READABLE"));
}

sub pool_needs_attention_status {
    my ($pool_name, $health) = @_;
    return (0, '') unless defined $pool_name && $pool_name =~ /^[A-Za-z0-9_.:\-]+$/;
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

sub action_health {
    print &ui_subheading(L("SUB_SYSTEM_HEALTH_REPORT"));
    
    print &ui_table_start(L("TABLE_HEALTH_CHECKS"), "width=100%", 2);
    
    my $pools = zpool_list();
    
    my $critical = 0;
    my $warning = 0;
    
    for my $pool (@$pools) {
        my $name = $pool->{name} || '';
        my $health = defined($pool->{health}) ? $pool->{health} : '';
        my $capacity = cap_pct_value($pool->{cap});
        
        if ($health ne 'ONLINE') {
            print &ui_table_row(L("VALUE_ALERT"), L("MSG_POOL_HEALTH_ALERT", $name, $health));
            $critical++;
        }

        my ($needs_attention, $attention_msg) = pool_needs_attention_status($name, $health);
        if ($needs_attention && $health eq 'ONLINE') {
            my $msg = L("MSG_POOL_ACTION_REQUIRED", $name);
            $msg .= ": " . &html_escape($attention_msg) if defined($attention_msg) && $attention_msg ne '';
            print &ui_table_row(L("VALUE_WARNING"), $msg);
            $warning++;
        }
        
        if ($capacity > 90) {
            print &ui_table_row(L("VALUE_WARNING"), L("MSG_POOL_CAPACITY_HIGH", $name, $capacity));
            $warning++;
        } elsif ($capacity > 80) {
            print &ui_table_row(L("VALUE_WARNING"), L("MSG_POOL_CAPACITY_WARN", $name, $capacity));
            $warning++;
        }
    }
    
    if ($critical == 0 && $warning == 0) {
        print &ui_table_row(L("COL_STATUS"), L("MSG_ALL_SYSTEMS_NOMINAL"));
    }
    
    print &ui_table_end();
    
    print &ui_subheading(L("SUB_RECOMMENDATIONS"));
    print "<ul>";
    print "<li>" . L("REC_MONITOR_CAPACITY") . "</li>";
    print "<li>" . L("REC_CHECK_SMART") . "</li>";
    print "<li>" . L("REC_MAINTAIN_SNAPSHOTS") . "</li>";
    print "<li>" . L("REC_REVIEW_SCRUB_LOGS") . "</li>";
    print "<li>" . L("REC_MONITOR_SYSTEM_LOGS") . "</li>";
    print "</ul>";
}

sub action_logs {
    print &ui_subheading(L("SUB_SYSTEM_LOGS"));
    
    print "<p>" . L("MSG_RECENT_MODULE_LOGS") . "</p>";
    
    my $log_file = '/var/log/webmin/zfsguru.log';
    
    if (-r $log_file) {
        my $lines = read_last_lines($log_file, 120);
        my $txt = join('', @$lines);
        print "<pre class='zfsguru-code-block'>" . &html_escape($txt) . "</pre>";
    } else {
        print &ui_print_error(L("ERR_LOGFILE_UNREADABLE"));
    }

    my $messages = '/var/log/messages';
    if (-r $messages) {
        print &ui_hr();
        print &ui_subheading(L("SUB_SYSTEM_MESSAGES_FILE"));
        my $lines = read_last_lines($messages, 120);
        my $txt = join('', @$lines);
        print "<pre class='zfsguru-code-block'>" . &html_escape($txt) . "</pre>";
    }
    
    print &ui_hr();
    print &ui_subheading(L("SUB_SYSTEM_MESSAGES"));
    
    my ($rc, $out, $err) = run_cmd('dmesg');
    if ($rc == 0 && $out) {
        my @lines = split /\n/, $out;
        my @recent = @lines > 50 ? @lines[-50..-1] : @lines;
        
        print "<pre>";
        for my $line (reverse @recent) {
            print &html_escape($line) . "\n";
        }
        print "</pre>";
    } else {
        print &ui_print_error(L("ERR_SYSTEM_MESSAGES_FAILED"));
    }
}

1;
