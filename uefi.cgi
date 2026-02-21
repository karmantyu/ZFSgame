#!/usr/bin/env perl

package main;

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/..";
use WebminCore;
use POSIX qw(strftime);
init_config();
eval { require './ZFSguru-lib.pl'; 1 } || require './zfsguru-lib.pl';
zfsguru_lib->import();
require 'ui-lib.pl';

our %config;

zfsguru_readparse();
zfsguru_init('en');

zfsguru_page_header(title_key => 'TITLE_UEFI');

eval { require_root(); };
if ($@) {
    &ui_print_error(L("ERROR_ROOT", $@));
    zfsguru_page_footer();
    exit 0;
}

eval { acl_require_feature('disks'); };
if ($@) {
    &ui_print_error(L("ERR_ACCESS_DENIED_FEATURE", 'disks'));
    zfsguru_page_footer();
    exit 0;
}

my $action = $in{'action'} || 'list';

if ($action eq 'manage') {
    action_manage();
} else {
    action_list();
}

my $back_url = 'index.cgi';
if ($action ne 'list') {
    $back_url = 'uefi.cgi?action=list';
    if (defined $in{'xnavigation'} && $in{'xnavigation'} =~ /^\d+$/) {
        $back_url .= '&xnavigation=' . $in{'xnavigation'};
    }
}
zfsguru_page_footer(url => $back_url);

sub action_list {
    print &ui_subheading(L("SUB_UEFI_ESP_LIST"));
    print "<p>" . L("MSG_UEFI_ESP_INTRO") . "</p>";

    my $esps = esp_partitions_list();

    my @heads = (
        L("COL_ESP_DEVICE"),
        L("COL_ESP_DISK"),
        L("COL_ESP_INDEX"),
        L("COL_ESP_LABEL"),
        L("COL_ESP_SIZE"),
        L("COL_ESP_MOUNT"),
        L("COL_ACTIONS"),
    );

    my @data;
    for my $e (@$esps) {
        my $dev = $e->{dev} || '';
        my $disk = $e->{disk} || '';
        my $idx  = defined $e->{index} ? $e->{index} : '';
        my $label = $e->{label} || '-';
        my $size = defined $e->{size_bytes} ? format_bytes($e->{size_bytes}) : '-';
        my $mnt = ($e->{mountpoints} && @{ $e->{mountpoints} })
            ? join(", ", @{ $e->{mountpoints} })
            : '-';
        my $link = "uefi.cgi?action=manage&dev=" . &url_encode($dev);
        my $btn = "<a class='button' href='" . &html_escape($link) . "'>" . &html_escape(L("BTN_MANAGE_ESP")) . "</a>";

        push @data, [
            &html_escape($dev),
            &html_escape($disk),
            &html_escape($idx),
            &html_escape($label),
            &html_escape($size),
            &html_escape($mnt),
            $btn,
        ];
    }

    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_ESP_LIST"), L("ERR_NO_ESP_FOUND"));
}

sub action_manage {
    my $dev = $in{'dev'} || '';
    $dev =~ s/^\s+|\s+$//g;
    my $esps = esp_partitions_list();
    my %by_dev = map { ($_->{dev} || '') => $_ } @$esps;
    my $esp = $by_dev{$dev};
    if (!$esp) {
        print &ui_print_error(L("ERR_ESP_DEVICE_INVALID", $dev));
        return;
    }

    my $bootmethod = sysctl_n('machdep.bootmethod');
    my $arch = sysctl_n('hw.machine_arch') || sysctl_n('hw.machine') || '';
    my $bootfile = uefi_bootfile_for_arch($arch);

    my $rel_freebsd = "EFI/FREEBSD/LOADER.EFI";
    my $rel_fallback = $bootfile ? "EFI/BOOT/$bootfile" : '';

    print &ui_subheading(L("SUB_ESP_MANAGE", $dev));

    print &ui_table_start(L("TABLE_ESP_INFO"), "width=100%", 2);
    print &ui_table_row(L("ROW_ESP_DEVICE"), &html_escape($dev));
    print &ui_table_row(L("ROW_ESP_DISK"), &html_escape($esp->{disk} || '-'));
    print &ui_table_row(L("ROW_ESP_INDEX"), &html_escape($esp->{index}));
    print &ui_table_row(L("ROW_ESP_LABEL"), &html_escape($esp->{label} || '-'));
    if (defined $esp->{size_bytes}) {
        print &ui_table_row(L("ROW_ESP_SIZE"), &html_escape(format_bytes($esp->{size_bytes})));
    }
    if ($bootmethod) {
        print &ui_table_row(L("ROW_UEFI_BOOTMETHOD"), &html_escape($bootmethod));
    }
    if ($arch) {
        print &ui_table_row(L("ROW_MACHINE_ARCH"), &html_escape($arch));
    }
    if ($bootfile) {
        print &ui_table_row(L("ROW_UEFI_FALLBACK"), &html_escape("EFI/BOOT/$bootfile"));
    } else {
        print &ui_table_row(L("ROW_UEFI_FALLBACK"), &html_escape(L("VALUE_UNKNOWN")));
    }
    my $mnt = $esp->{mountpoints} || [];
    my $mnt_disp = @$mnt ? join(", ", @$mnt) : '-';
    print &ui_table_row(L("ROW_ESP_MOUNTPOINTS"), &html_escape($mnt_disp));
    print &ui_table_end();

    my $sources = $esp->{sources} || [ $dev ];

    my $paths = bootcode_paths();
    my $src_module = $paths->{loader_efi} || '';
    my $src_system = $paths->{system_loader_efi} || '/boot/loader.efi';

    my $system_ok = ($src_system && -r $src_system) ? 1 : 0;
    my $module_ok = ($src_module && -r $src_module) ? 1 : 0;

    my @src_opts = ();
    push @src_opts, [
        'system',
        L("OPT_ESP_SOURCE_SYSTEM") . ($system_ok ? "" : " " . L("LBL_MISSING")),
        ($system_ok ? "" : "disabled=true")
    ] if $src_system;
    push @src_opts, [
        'module',
        L("OPT_ESP_SOURCE_MODULE") . ($module_ok ? "" : " " . L("LBL_MISSING")),
        ($module_ok ? "" : "disabled=true")
    ] if $src_module;

    if ($in{'do_install'} || $in{'do_backup'}) {
        handle_manage_post(
            dev          => $dev,
            sources      => $sources,
            rel_freebsd  => $rel_freebsd,
            rel_fallback => $rel_fallback,
            src_system   => $src_system,
            src_module   => $src_module,
            bootfile     => $bootfile,
        );
    }

    # Scan ESP files by doing a temporary read-only mount if needed
    my $scan = esp_scan_files($sources, $rel_freebsd, $rel_fallback);

    print &ui_hr();
    print &ui_subheading(L("SUB_ESP_FILES"));
    my @heads = (
        L("COL_ESP_PATH"),
        L("COL_ESP_EXISTS"),
        L("COL_ESP_SIZE"),
        L("COL_ESP_HINT"),
    );
    my @data;
    for my $row (@{ $scan->{files} || [] }) {
        push @data, [
            &html_escape($row->{rel} || '-'),
            &html_escape($row->{exists} ? L("VALUE_YES") : L("VALUE_NO")),
            &html_escape($row->{size} || '-'),
            &html_escape($row->{hint} || '-'),
        ];
    }
    print &ui_columns_table(\@heads, 100, \@data, undef, 1, L("TABLE_ESP_FILES"), L("VALUE_NONE"));
    if ($scan->{error}) {
        print &ui_alert(L("ERR_ESP_SCAN_FAILED", &html_escape($scan->{error})), "warning");
    }

    print &ui_hr();
    print &ui_subheading(L("SUB_ESP_INSTALL"));
    print "<p>" . L("MSG_ESP_INSTALL_DESC") . "</p>";

    print &ui_form_start("uefi.cgi", "post");
    print &ui_hidden("action", "manage");
    print &ui_hidden("dev", $dev);

    print &ui_table_start(L("TABLE_ESP_INSTALL"), "width=100%", 2);
    my $default_source = $system_ok ? 'system' : ($module_ok ? 'module' : 'system');
    print &ui_table_row(L("ROW_ESP_SOURCE"),
        &ui_select("esp_source", $default_source, \@src_opts));
    print &ui_table_row(L("ROW_ESP_TARGETS"),
        &ui_checkbox("target_freebsd", 1, L("LBL_TARGET_FREEBSD"), 1) . "<br />" .
        ($rel_fallback
            ? &ui_checkbox("target_fallback", 1, L("LBL_TARGET_FALLBACK", $bootfile), 0)
            : L("MSG_FALLBACK_UNAVAILABLE")));
    print &ui_table_row(L("ROW_CONFIRM_ESP_INSTALL"),
        &ui_checkbox("confirm_install", 1, L("LBL_CONFIRM_ESP_INSTALL"), 0));
    print &ui_table_row(L("ROW_CONFIRM_ESP_FALLBACK"),
        &ui_checkbox("confirm_fallback", 1, L("LBL_CONFIRM_ESP_FALLBACK"), 0));
    print &ui_table_end();

    print &ui_form_end([
        [ "do_backup", L("BTN_ESP_BACKUP") ],
        [ "do_install", L("BTN_ESP_INSTALL") ],
    ]);

    print &ui_hr();
    print &ui_subheading(L("SUB_ESP_TIPS"));
    print "<p>" . L("MSG_ESP_TIPS") . "</p>";
}

sub sysctl_n {
    my ($name) = @_;
    return '' unless defined $name && length $name;
    my ($rc, $out, $err) = run_cmd($zfsguru_lib::SYSCTL, '-n', $name);
    return '' if $rc != 0 || !defined $out;
    $out =~ s/\s+$//;
    return $out;
}

sub uefi_bootfile_for_arch {
    my ($arch) = @_;
    $arch ||= '';
    $arch =~ s/\s+//g;
    my $a = lc($arch);
    return 'BOOTX64.EFI'     if $a eq 'amd64' || $a eq 'x86_64';
    return 'BOOTIA32.EFI'    if $a eq 'i386'  || $a eq 'i686';
    return 'BOOTAA64.EFI'    if $a eq 'arm64' || $a eq 'aarch64';
    return 'BOOTARM.EFI'     if $a =~ /^arm/;
    return 'BOOTRISCV64.EFI' if $a eq 'riscv64';
    return '';
}

sub esp_partitions_list {
    my $disks = disk_list();
    my @rows;

    for my $d (@$disks) {
        my $plist = eval { gpart_list_partitions_info($d) };
        next if $@ || !defined $plist;

        my %by_index;
        if (ref($plist) eq 'HASH') {
            my $src = $plist->{by_index};
            %by_index = %{ $src || {} };
        } elsif (ref($plist) eq 'ARRAY') {
            for my $p (@$plist) {
                next unless ref($p) eq 'HASH';
                next unless defined $p->{index} && $p->{index} =~ /^\d+$/;
                $by_index{ int($p->{index}) } = $p;
            }
        } else {
            next;
        }

        for my $idx (sort { $a <=> $b } keys %by_index) {
            my $p = $by_index{$idx} || {};
            my $ptype = lc($p->{type} || '');
            my $rawtype = lc($p->{rawtype} || '');
            my $is_esp = 0;
            $is_esp = 1 if $ptype =~ /^(?:efi|efi-system|esp)$/;
            # GPT ESP type GUID (case-insensitive)
            $is_esp = 1 if $rawtype eq 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b';
            next unless $is_esp;
            my $name = $p->{name} || '';
            next unless length $name;
            my $dev = "/dev/$name";
            my $di = eval { diskinfo($name) };
            my $size = undef;
            $size = $di->{mediasize} if $di && defined $di->{mediasize} && $di->{mediasize} =~ /^\d+$/;
            my @sources = ($dev);
            if (defined $p->{label} && length $p->{label}) {
                push @sources, "/dev/gpt/" . $p->{label};
            }
            if (defined $p->{rawuuid} && length $p->{rawuuid}) {
                push @sources, "/dev/gptid/" . $p->{rawuuid};
            } elsif (defined $p->{uuid} && length $p->{uuid}) {
                push @sources, "/dev/gptid/" . $p->{uuid};
            }
            my $mnt = mountpoints_for_sources(\@sources);
            push @rows, {
                disk       => $d,
                index      => int($idx),
                name       => $name,
                dev        => $dev,
                label      => $p->{label} || '',
                rawuuid    => $p->{rawuuid} || $p->{uuid} || '',
                size_bytes => $size,
                sources    => \@sources,
                mountpoints => $mnt,
            };
        }
    }

    @rows = sort {
        ($a->{disk} cmp $b->{disk}) || ($a->{index} <=> $b->{index})
    } @rows;

    return \@rows;
}

sub esp_scan_files {
    my ($sources, $rel_freebsd, $rel_fallback) = @_;
    my @rels = grep { defined $_ && length $_ } ($rel_freebsd, $rel_fallback);
    my @files;
    my $err = '';

    eval {
        esp_with_mount($sources, 0, sub {
            my ($mp) = @_;
            for my $rel (@rels) {
                my $abs = "$mp/$rel";
                my $exists = -e $abs ? 1 : 0;
                my $size = $exists ? (-s $abs) : 0;
                my $hint = $exists ? file_hint($abs) : '';
                push @files, {
                    rel    => $rel,
                    exists => $exists,
                    size   => ($exists ? format_bytes($size) : '-'),
                    hint   => $hint,
                };
            }
        });
    };
    if ($@) {
        $err = "$@";
        $err =~ s/\s+$//;
    }

    return {
        files => \@files,
        error => $err,
    };
}

sub esp_with_mount {
    my ($sources, $rw, $code) = @_;
    die "Missing sources" unless ref($sources) eq 'ARRAY' && @$sources;
    die "Missing code" unless ref($code) eq 'CODE';

    my $mnt = mountpoints_for_sources($sources);
    if ($mnt && @$mnt) {
        return $code->($mnt->[0]);
    }

    my $dev = $sources->[0];
    my $mp = "/tmp/zfsguru-esp-" . time() . "-$$-" . int(rand(10000));
    mkdir $mp or die "mkdir $mp: $!";

    my @cmd = ($zfsguru_lib::MOUNT, '-t', 'msdosfs');
    if (!$rw) {
        push @cmd, '-o', 'ro';
    }
    push @cmd, $dev, $mp;

    my $mounted = 0;
    eval {
        must_run(@cmd);
        $mounted = 1;
        $code->($mp);
    };
    my $e = $@;

    my $umerr = '';
    if ($mounted) {
        eval { must_run($zfsguru_lib::UMOUNT, $mp); };
        if ($@) {
            $umerr = $@;
            $umerr =~ s/\s+$//;
        }
    }
    rmdir $mp if !$mounted || !$umerr;

    if ($e && $umerr) {
        die "$e\nAlso failed to unmount $mp: $umerr\n";
    }
    die $e if $e;
    die "Failed to unmount $mp: $umerr\n" if $umerr;
    return 1;
}

sub mountpoints_for_sources {
    my ($sources) = @_;
    return [] unless ref($sources) eq 'ARRAY' && @$sources;
    my %want = map { $_ => 1 } grep { defined $_ && length $_ } @$sources;
    return [] unless %want;

    my ($rc, $out, $err) = run_cmd($zfsguru_lib::MOUNT);
    return [] if $rc != 0 || !$out;
    my @mounts;
    for my $line (split /\n/, $out) {
        if ($line =~ /^(\S+)\s+on\s+(\S+)\s+/) {
            my ($src, $mp) = ($1, $2);
            push @mounts, $mp if $want{$src};
        }
    }
    my %seen;
    @mounts = grep { !$seen{$_}++ } @mounts;
    return \@mounts;
}

sub file_hint {
    my ($path) = @_;
    return '' unless defined $path && -r $path;
    open my $fh, '<', $path or return '';
    binmode($fh);
    my $buf = '';
    my $max = 1024 * 1024;
    my $n = sysread($fh, $buf, $max);
    close $fh;
    return '' unless defined $n && $n > 0;
    return ($buf =~ /FreeBSD/i) ? L("HINT_FREEBSD_LOADER") : '';
}

sub handle_manage_post {
    my (%opt) = @_;
    my $dev = $opt{dev} || '';
    my $sources = $opt{sources} || [ $dev ];
    my $rel_freebsd  = $opt{rel_freebsd} || '';
    my $rel_fallback = $opt{rel_fallback} || '';
    my $src_system   = $opt{src_system} || '';
    my $src_module   = $opt{src_module} || '';

    my $do_install = $in{'do_install'} ? 1 : 0;
    my $do_backup  = $in{'do_backup'} ? 1 : 0;

    my $target_freebsd  = $in{'target_freebsd'} ? 1 : 0;
    my $target_fallback = $in{'target_fallback'} ? 1 : 0;

    if (!$target_freebsd && !$target_fallback) {
        print &ui_print_error(L("ERR_ESP_NO_TARGETS"));
        return;
    }
    if ($target_fallback && !$rel_fallback) {
        print &ui_print_error(L("ERR_ESP_FALLBACK_UNAVAILABLE"));
        return;
    }

    if ($do_install) {
        if (!$in{'confirm_install'}) {
            print &ui_print_error(L("ERR_CONFIRM_ESP_INSTALL_REQUIRED"));
            return;
        }
        if ($target_fallback && !$in{'confirm_fallback'}) {
            print &ui_print_error(L("ERR_CONFIRM_ESP_FALLBACK_REQUIRED"));
            return;
        }
    } else {
        # backup only
        if (!$in{'confirm_install'}) {
            print &ui_print_error(L("ERR_CONFIRM_ESP_BACKUP_REQUIRED"));
            return;
        }
    }

    my $src = '';
    my $src_choice = $in{'esp_source'} || 'system';
    if ($src_choice eq 'module') {
        $src = $src_module;
    } else {
        $src = $src_system;
    }
    if ($do_install) {
        if (!defined $src || !length $src || !-r $src) {
            print &ui_print_error(L("ERR_ESP_SOURCE_MISSING", $src_choice, $src || '-'));
            return;
        }
    }

    my @targets;
    push @targets, $rel_freebsd if $target_freebsd;
    push @targets, $rel_fallback if $target_fallback;

    my @done;
    my @backups;
    eval {
        esp_with_mount($sources, 1, sub {
            my ($mp) = @_;
            my $ts = strftime("%Y%m%d-%H%M%S", localtime());
            for my $rel (@targets) {
                next unless defined $rel && length $rel;
                die "Invalid rel path" if $rel =~ /\.\./;
                my $abs = "$mp/$rel";
                my $dir = $abs;
                $dir =~ s{/[^/]+$}{};
                mkdir_p($dir);

                if (-e $abs) {
                    my $bak = $abs . ".bak-" . $ts;
                    must_run($zfsguru_lib::CP, '-f', $abs, $bak);
                    push @backups, $bak;
                }

                if ($do_install) {
                    must_run($zfsguru_lib::CP, '-f', $src, $abs);
                    push @done, $rel;
                } else {
                    push @done, $rel;
                }
            }
        });
    };
    if ($@) {
        print &ui_print_error(L("ERR_ESP_ACTION_FAILED", $@));
        return;
    }

    if ($do_install) {
        my $msg = L("SUCCESS_ESP_INSTALLED", join(', ', @done));
        if (@backups) {
            $msg .= "<br />" . L("MSG_ESP_BACKUPS_CREATED", join(', ', @backups));
        }
        print &ui_print_success($msg);
    } else {
        my $msg = L("SUCCESS_ESP_BACKED_UP", join(', ', @done));
        if (@backups) {
            $msg .= "<br />" . L("MSG_ESP_BACKUPS_CREATED", join(', ', @backups));
        } else {
            $msg .= "<br />" . L("MSG_ESP_NO_FILES_TO_BACKUP");
        }
        print &ui_print_success($msg);
    }
}

sub mkdir_p {
    my ($path) = @_;
    die "Invalid path" unless defined $path && $path =~ m{^/};
    my @parts = split '/', $path;
    my $cur = '';
    for my $p (@parts) {
        next unless length $p;
        $cur .= "/$p";
        next if -d $cur;
        mkdir $cur or die "mkdir $cur: $!";
    }
    return 1;
}

sub format_bytes {
    my ($bytes) = @_;
    return '-' unless defined $bytes && $bytes =~ /^\d+$/;
    my @units = qw(B KB MB GB TB);
    my $size = $bytes + 0;
    my $unit_idx = 0;

    while ($size >= 1024 && $unit_idx < @units - 1) {
        $size /= 1024;
        $unit_idx++;
    }
    return sprintf("%.2f %s", $size, $units[$unit_idx]);
}
