package zfsguru_lib;

use strict;
use warnings;
use Exporter ();
use POSIX qw(strftime setsid);
use File::Basename qw(basename dirname);
use Cwd qw(abs_path);
use Text::ParseWords qw(shellwords);
use Digest::SHA ();

my $LIBDIR = dirname(abs_path(__FILE__) || __FILE__);
require "$LIBDIR/zfsguru_i18n.pl";

# Export all public helpers into CGI package (usually main).
sub import {
  my ($class)=@_;
  no strict 'refs';
  my $caller = caller;
  for my $name (keys %{"${class}::"}) {
    next if $name =~ /^_/;
    next if $name =~ /^(?:BEGIN|END|import)$/;
    next unless defined &{"${class}::$name"};
    *{"${caller}::$name"} = \&{"${class}::$name"};
  }
}

our (%config, $module_root_directory);
my (%_file_cfg, $_file_cfg_loaded, $_file_cfg_path, $_file_cfg_mtime);
our (
  $ZPOOL,$ZFS,$GEOM,$GSTAT,$MD,$MOUNT,$UMOUNT,$TAR,$CP,$MV,$RM,$CHMOD,$CHOWN,$FIND,
  $SYSCTL,$DISKINFO,$SMARTCTL,$CAMCONTROL,$DD,$NEWFS,$BLKDISCARD,$ATA_SECURE_ERASE,
  $ATA_SECURE_ERASE_ARGS,$ATA_SECURE_ERASE_PASS,$ATA_SECURE_ERASE_MODE,$IFCONFIG,
  $SOCKSTAT,$PFCTL,$SHUTDOWN,$SERVICE,$FREEBSD_UPDATE,$PKG,$FETCH,$GLABEL,$GPART,
  $SWAPCTL,$SWAPON,$SWAPOFF,$LOGGER,$LOG_FILE,$CONFIG_BACKUP_DIR
);

sub _refresh_ctx {
  no warnings 'once';
  %config = %main::config if %main::config;
  $module_root_directory = $main::module_root_directory if defined $main::module_root_directory;
}
sub _module_cfg_file {
  _refresh_ctx();
  return (($module_root_directory || $LIBDIR) . '/config.txt');
}
sub _load_file_cfg {
  my $f = _module_cfg_file();
  return if !defined $f || $f eq '';
  my $mt = (-e $f) ? ((stat($f))[9] || 0) : -1;
  if ($_file_cfg_loaded && defined $_file_cfg_path && $_file_cfg_path eq $f && defined $_file_cfg_mtime && $_file_cfg_mtime == $mt) {
    return;
  }
  %_file_cfg = ();
  if (-r $f && open(my $fh, '<', $f)) {
    while (my $ln = <$fh>) {
      chomp $ln;
      $ln =~ s/\r$//;
      $ln =~ s/^\s+|\s+$//g;
      next if $ln eq '' || $ln =~ /^#/;
      next unless $ln =~ /^([A-Za-z0-9_]+)\s*=\s*(.*)$/;
      my ($k,$v)=($1,$2);
      $v =~ s/^\s+|\s+$//g;
      $_file_cfg{$k} = $v;
    }
    close($fh);
  }
  $_file_cfg_loaded = 1;
  $_file_cfg_path = $f;
  $_file_cfg_mtime = $mt;
}
sub _cfg {
  my ($k,$d)=@_;
  _load_file_cfg();
  return $_file_cfg{$k} if exists $_file_cfg{$k} && defined $_file_cfg{$k} && $_file_cfg{$k} ne '';
  return $config{$k} if defined $config{$k} && $config{$k} ne '';
  return $d;
}
sub _resolve_module_path {
  my ($p)=@_;
  return '' unless defined $p;
  $p =~ s/^\s+|\s+$//g;
  return '' if $p eq '';
  return $p if $p =~ m{^/};
  $p =~ s{^\./}{};
  return ($module_root_directory || $LIBDIR) . '/' . $p;
}

sub _init_paths {
  _refresh_ctx();
  $ZPOOL=_cfg('zpool_cmd','/sbin/zpool');
  $ZFS=_cfg('zfs_cmd','/sbin/zfs');
  $GEOM=_cfg('geom_cmd','/sbin/geom');
  $GSTAT=_cfg('gstat_cmd','/usr/sbin/gstat');
  $MD=_cfg('mdconfig_cmd','/sbin/mdconfig');
  $MOUNT=_cfg('mount_cmd','/sbin/mount');
  $UMOUNT=_cfg('umount_cmd','/sbin/umount');
  $TAR=_cfg('tar_cmd','/usr/bin/tar');
  $CP=_cfg('cp_cmd','/bin/cp');
  $MV=_cfg('mv_cmd','/bin/mv');
  $RM=_cfg('rm_cmd','/bin/rm');
  $CHMOD=_cfg('chmod_cmd','/bin/chmod');
  $CHOWN=_cfg('chown_cmd','/usr/sbin/chown');
  $FIND=_cfg('find_cmd','/usr/bin/find');
  $SYSCTL=_cfg('sysctl_cmd','/sbin/sysctl');
  $DISKINFO=_cfg('diskinfo_cmd','/usr/sbin/diskinfo');
  $SMARTCTL=_cfg('smartctl_cmd','/usr/local/sbin/smartctl');
  $CAMCONTROL=_cfg('camcontrol_cmd','/sbin/camcontrol');
  $DD=_cfg('dd_cmd','/bin/dd');
  $NEWFS=_cfg('newfs_cmd','/sbin/newfs');
  $BLKDISCARD=_cfg('blkdiscard_cmd','/sbin/blkdiscard');
  $ATA_SECURE_ERASE=_cfg('ata_secure_erase_cmd','');
  $ATA_SECURE_ERASE_ARGS=_cfg('ata_secure_erase_args','./scripts/ata_secure_erase_camcontrol.sh');
  $ATA_SECURE_ERASE_PASS=_cfg('ata_secure_erase_pass','');
  $ATA_SECURE_ERASE_MODE=_cfg('ata_secure_erase_mode','');
  $IFCONFIG=_cfg('ifconfig_cmd','/sbin/ifconfig');
  $SOCKSTAT=_cfg('sockstat_cmd','/usr/bin/sockstat');
  $PFCTL=_cfg('pfctl_cmd','/sbin/pfctl');
  $SHUTDOWN=_cfg('shutdown_cmd','/sbin/shutdown');
  $SERVICE=_cfg('service_cmd','/usr/sbin/service');
  $FREEBSD_UPDATE=_cfg('freebsd_update_cmd','/usr/sbin/freebsd-update');
  $PKG=_cfg('pkg_cmd','/usr/local/sbin/pkg');
  $FETCH=_cfg('fetch_cmd','/usr/bin/fetch');
  $GLABEL=_cfg('glabel_cmd','/sbin/glabel');
  $GPART=_cfg('gpart_cmd','/sbin/gpart');
  $SWAPCTL=_cfg('swapctl_cmd','/sbin/swapctl');
  $SWAPON=_cfg('swapon_cmd','/sbin/swapon');
  $SWAPOFF=_cfg('swapoff_cmd','/sbin/swapoff');
  $LOGGER=_cfg('logger_cmd','/usr/bin/logger');
  $LOG_FILE=_cfg('log_file','/var/log/webmin/zfsguru.log');
  $CONFIG_BACKUP_DIR=_cfg('config_backup_dir','/var/tmp/zfsguru-config-backups');
}
_init_paths();

sub _q { my ($s)=@_; $s='' unless defined $s; $s =~ s/'/'"'"'/g; return "'$s'"; }
sub _cmdstr { join(' ', map { _q($_) } @_); }

sub log_info  { _log('INFO', @_); }
sub log_warn  { _log('WARN', @_); }
sub log_error { _log('ERROR', @_); }
sub _log {
  my ($lvl,$msg)=@_;
  _init_paths();
  my $line='['.strftime('%Y-%m-%d %H:%M:%S',localtime())."] [$lvl] $msg\n";
  eval {
    my $d = dirname($LOG_FILE || '/var/log/webmin/zfsguru.log');
    mkdir $d if $d && !-d $d;
    open my $fh,'>>',$LOG_FILE or return;
    print $fh $line;
    close $fh;
  };
}

sub command_exists {
  my ($cmd)=@_;
  return 0 unless defined $cmd && length $cmd;
  return -x $cmd ? 1 : 0 if $cmd =~ m{/};
  return 0 unless $cmd =~ /^[A-Za-z0-9._+-]+$/;
  my $path = $ENV{'PATH'} // '/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin';
  for my $d (split /:/, $path) {
    next unless defined $d && length $d;
    my $p = $d . '/' . $cmd;
    return 1 if -x $p;
  }
  return 0;
}

sub run_cmd {
  my @cmd=@_;
  _init_paths();
  return (127,'','empty command') unless @cmd;
  my $cmd=_cmdstr(@cmd);
  my $out=`$cmd 2>&1`;
  my $rc=$?>>8;
  my $err=$rc==0?'':$out;
  log_info("cmd ok: $cmd") if $rc==0;
  log_warn("cmd rc=$rc: $cmd :: $err") if $rc!=0;
  return ($rc,$out,$err);
}

sub run_cmd_input {
  my ($input,@cmd)=@_;
  return (127,'','empty command') unless @cmd;
  my $base='/tmp/zfsguru_cmd_'.$$.'_'.int(rand(1000000));
  my ($of,$ef)=($base.'.out',$base.'.err');
  my $cmd=_cmdstr(@cmd).' >'._q($of).' 2>'._q($ef);
  my $rc=127;
  eval {
    open my $ph,'|-','/bin/sh','-c',$cmd or die 'pipe failed';
    print $ph (defined $input ? $input : '');
    close $ph;
    $rc=$?>>8;
  };
  my ($out,$err)=('','');
  if (-r $of) { open my $f,'<',$of; local $/; $out=<$f>; close $f; }
  if (-r $ef) { open my $f,'<',$ef; local $/; $err=<$f>; close $f; }
  unlink $of if -e $of;
  unlink $ef if -e $ef;
  return ($rc,$out,$err);
}

sub must_run {
  my @cmd=@_;
  my ($rc,$out,$err)=run_cmd(@cmd);
  die($err || $out || 'command failed') if $rc!=0;
  return wantarray ? ($out,$err) : $out;
}

sub _zfsguru_url_decode {
  my ($s)=@_;
  $s='' unless defined $s;
  $s =~ tr/+/ /;
  $s =~ s/%([0-9A-Fa-f]{2})/chr(hex($1))/eg;
  return $s;
}
sub _zfsguru_parse_urlencoded_into {
  my ($raw,$out)=@_;
  return unless defined $raw && length $raw;
  for my $pair (split /[&;]/,$raw) {
    next unless length $pair;
    my ($k,$v)=split(/=/,$pair,2);
    $k=_zfsguru_url_decode($k);
    $v=_zfsguru_url_decode(defined $v ? $v : '');
    next unless length $k;
    if (exists $out->{$k}) { $out->{$k}.="\0".$v; }
    else { $out->{$k}=$v; }
  }
}
sub _zfsguru_read_stdin {
  my $len=$ENV{'CONTENT_LENGTH'}||0;
  return '' unless $len =~ /^\d+$/ && $len>0;
  my ($buf,$left)=('', $len);
  while ($left>0) {
    my $chunk='';
    my $n=read(STDIN,$chunk,$left);
    last unless defined $n && $n>0;
    $buf.=$chunk; $left-=$n;
  }
  return $buf;
}
sub _zfsguru_store_input {
  my ($caller,$inref)=@_;
  no strict 'refs';
  if ($caller && $caller =~ /^[A-Za-z_]\w*(?:::\w+)*$/) { %{"${caller}::in"}=%$inref; }
  %{'main::in'}=%$inref;
}
sub _zfsguru_current_input_copy {
  my ($caller)=@_;
  my %cur;
  no strict 'refs';
  if ($caller && $caller =~ /^[A-Za-z_]\w*(?:::\w+)*$/) {
    my $href=\%{"${caller}::in"};
    %cur=%$href if $href && %$href;
  }
  if (!%cur) { my $mref=\%{'main::in'}; %cur=%$mref if $mref && %$mref; }
  return %cur;
}
sub _zfsguru_post_parse_fixup {
  my ($caller)=@_;
  my %cur=_zfsguru_current_input_copy($caller);
  my %q; _zfsguru_parse_urlencoded_into($ENV{'QUERY_STRING'}||'',\%q);
  for my $k (keys %q) { $cur{$k}=$q{$k}; }
  for my $k (keys %cur) {
    next unless defined $cur{$k};
    my $v=$cur{$k};
    if ($v =~ /[&;]/ && $v =~ /[A-Za-z0-9_]+=/) {
      my %extra; _zfsguru_parse_urlencoded_into($v,\%extra);
      if (%extra) {
        my ($first)=split(/[&;]/,$v,2);
        $cur{$k}=_zfsguru_url_decode($first);
        for my $ek (keys %extra) { $cur{$ek}=$extra{$ek} unless exists $cur{$ek}; }
      }
    }
    $cur{$k} =~ s/\0.*$//s;
  }
  _zfsguru_store_input($caller,\%cur);
  return 1;
}
sub _zfsguru_readparse_fallback {
  my ($caller)=@_;
  my %parsed;
  _zfsguru_parse_urlencoded_into($ENV{'QUERY_STRING'}||'',\%parsed);
  my $method=uc($ENV{'REQUEST_METHOD'}||'GET');
  if ($method eq 'POST') {
    my $ctype=$ENV{'CONTENT_TYPE'}||'';
    my $body=_zfsguru_read_stdin();
    if ($ctype =~ m{application/x-www-form-urlencoded}i || $ctype eq '') {
      _zfsguru_parse_urlencoded_into($body,\%parsed);
    }
  }
  _zfsguru_store_input($caller,\%parsed);
  return 1;
}
sub _zfsguru_try_parser {
  my ($fq)=@_;
  return 0 unless $fq;
  no strict 'refs';
  return 0 unless defined &{$fq};
  my $ok=eval { &{$fq}(); 1; };
  return $ok ? 1 : 0;
}
sub zfsguru_readparse {
  my $caller=caller;
  return _zfsguru_post_parse_fixup($caller) if $caller && _zfsguru_try_parser("${caller}::ReadParse");
  return _zfsguru_post_parse_fixup($caller) if _zfsguru_try_parser('main::ReadParse');
  return _zfsguru_post_parse_fixup($caller) if _zfsguru_try_parser('WebminCore::ReadParse');
  return _zfsguru_readparse_fallback($caller);
}
sub zfsguru_readparse_mime {
  my $caller=caller;
  return _zfsguru_post_parse_fixup($caller) if $caller && _zfsguru_try_parser("${caller}::ReadParseMime");
  return _zfsguru_post_parse_fixup($caller) if _zfsguru_try_parser('main::ReadParseMime');
  return _zfsguru_post_parse_fixup($caller) if _zfsguru_try_parser('WebminCore::ReadParseMime');
  return zfsguru_readparse();
}

sub is_pool_name { defined($_[0]) && $_[0] =~ /^[A-Za-z][A-Za-z0-9_.:\-]*$/ ? 1 : 0; }
sub is_dataset_name { defined($_[0]) && $_[0] =~ /^[A-Za-z0-9_.:\-]+(?:\/[A-Za-z0-9_.:\-]+)*$/ ? 1 : 0; }
sub is_snapshot_fullname { defined($_[0]) && $_[0] =~ /^[A-Za-z0-9_.:\-]+(?:\/[A-Za-z0-9_.:\-]+)*\@[A-Za-z0-9_.:\-]+$/ ? 1 : 0; }
sub is_mountpoint { defined($_[0]) && ($_[0] =~ m{^/[A-Za-z0-9_./\-]*$} || $_[0] =~ /^(?:legacy|none)$/) ? 1 : 0; }
sub is_property { defined($_[0]) && $_[0] =~ /^[A-Za-z][A-Za-z0-9_:\-]*$/ ? 1 : 0; }
sub is_boolean { defined($_[0]) && $_[0] =~ /^(?:0|1|yes|no|on|off|true|false)$/i ? 1 : 0; }
sub is_integer { defined($_[0]) && $_[0] =~ /^-?\d+$/ ? 1 : 0; }
sub is_zfs_size { defined($_[0]) && ($_[0] =~ /^(?:none|auto)$/i || $_[0] =~ /^\d+(?:[KMGTP]i?B?|%)?$/i) ? 1 : 0; }
sub is_label_name { defined($_[0]) && $_[0] =~ /^[A-Za-z0-9_.\-]+$/ ? 1 : 0; }
sub is_disk_name { defined($_[0]) && $_[0] =~ /^[A-Za-z][A-Za-z0-9_.:\-]*$/ ? 1 : 0; }
sub _normalize_dev_path { my ($d)=@_; return undef unless defined $d; $d =~ s/^\s+|\s+$//g; $d =~ s{^/dev/}{}; return undef unless $d =~ m{^[A-Za-z0-9_./:\-]+$}; return '/dev/'.$d; }
sub url_encode { my ($s)=@_; $s='' unless defined $s; $s =~ s/([^A-Za-z0-9\-_.~])/sprintf('%%%02X',ord($1))/eg; return $s; }

sub ensure_dir { my ($d)=@_; return 0 unless $d; return 1 if -d $d; eval { mkdir $d }; return -d $d ? 1 : 0; }
sub read_file_text {
  my ($p)=@_;
  return '' unless defined $p && -r $p;
  open my $fh,'<',$p or return '';
  local $/;
  my $txt=<$fh>;
  close $fh;
  return defined $txt ? $txt : '';
}
sub write_file_with_backup {
  my ($path,$content)=@_;
  die 'Invalid path' unless defined $path && $path =~ m{^/};
  ensure_dir($CONFIG_BACKUP_DIR);
  my $bak='';
  if (-e $path) {
    $bak = $CONFIG_BACKUP_DIR.'/'.basename($path).'.'.strftime('%Y%m%d-%H%M%S',localtime()).'.bak';
    my ($rc,$out,$err)=run_cmd($CP,'-f',$path,$bak);
    die('Backup failed: '.$err) if $rc!=0;
  }
  open my $fh,'>',$path or die "Cannot write $path: $!";
  print $fh (defined $content ? $content : '');
  close $fh;
  return $bak;
}
sub copy_text_file { my ($src,$dst)=@_; my ($rc,$out,$err)=run_cmd($CP,'-f',$src,$dst); die $err if $rc!=0; 1; }
sub rc_conf_value {
  my ($file,$key)=@_;
  $file ||= '/etc/rc.conf';
  return undef unless $key && $key =~ /^[A-Za-z0-9_]+$/;
  my $txt=read_file_text($file);
  for my $ln (split /\n/,$txt) {
    next if $ln =~ /^\s*#/;
    return $1 if $ln =~ /^\s*\Q$key\E\s*=\s*"?([^"\n]*)"?\s*$/;
  }
  return undef;
}
sub set_rc_conf_value {
  my ($file,$key,$val)=@_;
  $file ||= '/etc/rc.conf';
  die 'Invalid key' unless $key && $key =~ /^[A-Za-z0-9_]+$/;
  $val='' unless defined $val;
  my @lines;
  if (-e $file) { open my $in,'<',$file or die "Cannot read $file: $!"; @lines=<$in>; close $in; }
  my $entry = $key.'="'.$val."\"\n";
  my $found=0;
  for my $i (0..$#lines) {
    if ($lines[$i] =~ /^\s*\Q$key\E\s*=/) { $lines[$i]=$entry; $found=1; last; }
  }
  push @lines,$entry unless $found;
  open my $out,'>',$file or die "Cannot write $file: $!";
  print $out @lines;
  close $out;
  1;
}
sub require_root { return 1 if $>==0 || $<==0; die 'Root privileges required'; }

sub zfsguru_jobs_dir {
  _refresh_ctx();
  my $d = $config{'jobs_dir'} || '/var/tmp/zfsguru-jobs';
  ensure_dir($d);
  return $d;
}
sub _job_time { strftime('%Y-%m-%d %H:%M:%S', localtime(shift || time())); }
sub zfsguru_start_job {
  my (%opt)=@_;
  my $prefix=$opt{'prefix'} || 'job';
  $prefix =~ s/[^A-Za-z0-9_.-]/_/g;
  my $title=$opt{'title'}||$prefix;
  my $run=$opt{'run'};
  my $commands=$opt{'commands'};
  my $id=$prefix.'_'.strftime('%Y%m%d_%H%M%S',localtime()).'_'.$$;
  my $log_file=$id.'.log';
  my $jobs_dir=zfsguru_jobs_dir();
  return (0,undef,undef,'job directory is not available') unless $jobs_dir && -d $jobs_dir;
  my $log_path=$jobs_dir.'/'.$log_file;
  my $pre;
  if (!open($pre, '>>', $log_path)) {
    return (0,undef,undef,"cannot create job log: $!");
  }
  print $pre '['._job_time()."] JOB_QUEUED id=$id title=$title\n";
  close $pre;
  my $pid=fork();
  return (0,undef,undef,'fork failed') unless defined $pid;
  if ($pid > 0 && open(my $pfh, '>>', $log_path)) {
    print $pfh '['._job_time()."] JOB_CHILD_PID=$pid\n";
    close $pfh;
  }
  if ($pid==0) {
    # Detach the worker from the CGI/session process group so it can outlive request teardown.
    eval { setsid(); 1; };
    $SIG{'HUP'} = 'IGNORE';

    my $status_fh;
    my $streams_redirected = 0;
    if (open($status_fh, '>>', $log_path)) {
      # Some environments can throw ioctl-related errors on autoflush toggling.
      eval {
        my $old = select($status_fh);
        $| = 1;
        select($old);
      };
      # Route worker stdout/stderr to the same job log so callback prints are captured
      # and do not write into a closed CGI socket (which would raise SIGPIPE).
      eval {
        open(STDOUT, '>>&', $status_fh) or die "dup stdout failed: $!";
        open(STDERR, '>>&', $status_fh) or die "dup stderr failed: $!";
        select(STDOUT);
        $| = 1;
        $streams_redirected = 1;
      };
      if (!$streams_redirected) {
        eval {
          open(STDOUT, '>>', $log_path) or die "reopen stdout failed: $!";
          open(STDERR, '>>', $log_path) or die "reopen stderr failed: $!";
          select(STDOUT);
          $| = 1;
          $streams_redirected = 1;
        };
      }
    } else {
      # Last resort: never write background output to CGI socket.
      eval {
        open(STDOUT, '>', '/dev/null') or die "redirect stdout failed: $!";
        open(STDERR, '>', '/dev/null') or die "redirect stderr failed: $!";
        select(STDOUT);
        $| = 1;
      };
    }
    my $append_fallback = sub {
      my ($line) = @_;
      return unless defined $line && length $line;
      if (open(my $fh, '>>', $log_path)) {
        print $fh $line . "\n";
        close $fh;
      }
    };
    my $job_note = sub {
      my ($line) = @_;
      return unless defined $line && length $line;
      my $payload = '['._job_time()."] $line";
      if ($status_fh) {
        print $status_fh $payload . "\n";
      } else {
        $append_fallback->($payload);
      }
    };
    my $job_write = sub {
      my ($txt) = @_;
      return unless defined $txt && length $txt;
      if ($status_fh) {
        print $status_fh $txt;
      } else {
        for my $ln (split /\n/, $txt) {
          $append_fallback->($ln);
        }
      }
    };
    my $job_signal = sub {
      my ($sig) = @_;
      eval {
        $job_note->("JOB_SIGNAL=$sig");
        $job_note->('JOB_STATUS=FAILED');
      };
      close($status_fh) if $status_fh;
      exit 1;
    };
    # SIGPIPE can occur if any legacy handle still points to a closed client socket.
    # Ignore it so background jobs are not marked failed for transport-side events.
    $SIG{'PIPE'} = 'IGNORE';
    for my $sig (qw(INT TERM QUIT ABRT ALRM USR1 USR2)) {
      $SIG{$sig} = sub { $job_signal->($sig); };
    }
    eval {
      $job_note->("JOB_START id=$id title=$title");
      if (ref($opt{'env'}) eq 'HASH') { for my $k (keys %{ $opt{'env'} }) { $ENV{$k}=$opt{'env'}->{$k}; } }
      if (ref($commands) eq 'ARRAY' && @$commands) {
        for my $cmd (@$commands) {
          if (ref($cmd) eq 'ARRAY') {
            my ($rc,$out,$err)=run_cmd(@$cmd);
            $job_write->($out) if defined $out;
            die($err || 'command failed') if $rc!=0;
          } elsif (defined($cmd) && !ref($cmd) && length($cmd)) {
            my ($rc,$out,$err)=run_cmd('/bin/sh','-c',$cmd);
            $job_write->($out) if defined $out;
            die($err || 'command failed') if $rc!=0;
          }
        }
      }
      elsif (ref($run) eq 'CODE') {
        if ($status_fh) {
          local *STDOUT = $status_fh;
          local *STDERR = $status_fh;
          $run->();
        } else {
          $run->();
        }
      }
      elsif (ref($run) eq 'ARRAY') { my ($rc,$out,$err)=run_cmd(@$run); $job_write->($out) if defined $out; die $err if $rc!=0; }
      elsif (defined $run && !ref($run) && length($run)) { my ($rc,$out,$err)=run_cmd('/bin/sh','-c',$run); $job_write->($out) if defined $out; die $err if $rc!=0; }
      $job_note->('JOB_STATUS=OK');
      exit 0;
    };
    if ($@) {
      $job_note->('JOB_STATUS=FAILED');
      $job_note->("ERROR: $@");
    }
    close($status_fh) if $status_fh;
    exit 1;
  }
  return (1,$id,$log_file,undef);
}
sub zfsguru_list_jobs {
  my (%opt)=@_;
  my $prefix=$opt{'prefix'}||'';
  my $limit=$opt{'limit'};
  my $dir=zfsguru_jobs_dir();
  return [] unless -d $dir;
  opendir my $dh,$dir or return [];
  my @files=grep { /\.log$/ && (!$prefix || index($_,$prefix.'_')==0) } readdir($dh);
  closedir $dh;
  my @rows;
  for my $f (@files) {
    my $p="$dir/$f"; next unless -f $p;
    my @st=stat($p); my $mt=$st[9]||0;
    my $txt=read_file_text($p);
    my @pids = ($txt =~ /JOB_CHILD_PID=(\d+)/mg);
    my $pid;
    for my $cand (@pids) {
      next unless defined $cand && $cand =~ /^\d+$/;
      next if $cand == 0;
      $pid = $cand;
    }
    my $status = $txt =~ /JOB_STATUS=OK/m ? 'ok'
               : $txt =~ /JOB_STATUS=FAILED/m ? 'failed'
               : $txt =~ /JOB_STATUS=KILLED/m ? 'killed'
               : 'running';
    if ($status eq 'running') {
      my $alive = (defined($pid) && $pid =~ /^\d+$/) ? (kill 0, $pid) : 0;
      $status = 'stale' unless $alive;
    }
    push @rows,{file=>$f,status=>$status,pid=>$pid,mtime=>_job_time($mt),mtime_epoch=>$mt};
  }
  @rows=sort { $b->{mtime_epoch} <=> $a->{mtime_epoch} } @rows;
  splice(@rows,$limit) if defined($limit) && $limit =~ /^\d+$/ && $limit>0 && @rows>$limit;
  return \@rows;
}
sub zfsguru_kill_job {
  my (%opt)=@_;
  my $f=$opt{'file'}||'';
  return (0,'invalid job file') unless $f =~ /^[A-Za-z0-9_.\-]+\.log$/;
  my $p = zfsguru_jobs_dir().'/'.$f;
  return (0,'job log not found') unless -f $p;
  my $txt = read_file_text($p);
  my @pids = ($txt =~ /JOB_CHILD_PID=(\d+)/mg);
  my $pid;
  for my $cand (@pids) {
    next unless defined $cand && $cand =~ /^\d+$/;
    next if $cand == 0;
    $pid = $cand;
  }
  if (!defined($pid) || $pid !~ /^\d+$/) {
    return (1,'job already finished') if $txt =~ /JOB_STATUS=(?:OK|FAILED|KILLED)/m;
    return (0,'job pid not found in log (old or incomplete job log)');
  }
  my $alive = kill 0, $pid;
  if (!$alive) {
    if ($txt !~ /JOB_STATUS=(?:OK|FAILED|KILLED)/m) {
      if (open(my $fh,'>>',$p)) {
        print $fh '['._job_time()."] JOB_STATUS=KILLED\n";
        print $fh "ERROR: process not running (pid=$pid)\n";
        close $fh;
      }
    }
    return (1,'job already finished');
  }
  kill 'TERM', $pid;
  select(undef, undef, undef, 1.0);
  $alive = kill 0, $pid;
  if ($alive) {
    kill 'KILL', $pid;
    select(undef, undef, undef, 0.5);
    $alive = kill 0, $pid;
  }
  if (open(my $fh,'>>',$p)) {
    print $fh '['._job_time()."] JOB_STATUS=KILLED\n";
    print $fh "ERROR: terminated by user\n";
    close $fh;
  }
  return $alive ? (0,'failed to terminate job process') : (1,'job terminated');
}
sub zfsguru_read_job_log {
  my (%opt)=@_;
  my $f=$opt{'file'}||'';
  return '' unless $f =~ /^[A-Za-z0-9_.\-]+\.log$/;
  return read_file_text(zfsguru_jobs_dir().'/'.$f);
}
sub zfsguru_clear_job_logs {
  my (%opt)=@_;
  my $prefix = $opt{'prefix'} || '';
  my $dir = zfsguru_jobs_dir();
  return (0,'jobs directory is not available',0) unless $dir && -d $dir;
  opendir my $dh, $dir or return (0,"cannot open jobs directory: $!",0);
  my @files = grep { /\.log$/ && (!$prefix || index($_, $prefix.'_') == 0) } readdir($dh);
  closedir $dh;
  my $count = 0;
  for my $f (@files) {
    my $p = "$dir/$f";
    next unless -f $p;
    if (unlink($p)) {
      $count++;
    }
  }
  return (1,undef,$count);
}
# zpool / zfs -------------------------------------------------------------
sub zpool_list {
  my ($rc,$out,$err)=run_cmd($ZPOOL,'list','-H','-o','name,size,alloc,free,cap,health');
  return [] if $rc!=0 || !$out;
  my @rows;
  for my $ln (split /\n/,$out) {
    next unless $ln =~ /\S/;
    my @p=split /\t+|\s+/,$ln;
    next unless @p>=6;
    push @rows,{name=>$p[0],size=>$p[1],alloc=>$p[2],free=>$p[3],cap=>$p[4],health=>$p[5]};
  }
  return \@rows;
}
sub zpool_status {
  my ($pool)=@_;
  my @cmd=($ZPOOL,'status');
  push @cmd,$pool if defined $pool && $pool ne '';
  my ($rc,$out,$err)=run_cmd(@cmd);
  return undef if $rc!=0;
  return $out;
}
sub parse_zpool_status {
  my ($txt)=@_; $txt='' unless defined $txt;
  my @p; my $cur; my $in=0;
  for my $ln (split /\n/,$txt) {
    if ($ln =~ /^\s*pool:\s*(\S+)/) { $cur={name=>$1,devices=>[]}; push @p,$cur; $in=0; next; }
    next unless $cur;
    if ($ln =~ /^\s*state:\s*(.+)$/) { $cur->{state}=$1; next; }
    if ($ln =~ /^\s*status:\s*(.+)$/) { $cur->{status}=$1; next; }
    if ($ln =~ /^\s*config:/) { $in=1; next; }
    if ($in && $ln =~ /^\s+(\S+)\s+(ONLINE|OFFLINE|DEGRADED|FAULTED|UNAVAIL|REMOVED|AVAIL|INUSE)/i) {
      my ($d,$st)=($1,uc($2));
      next if $d =~ /^(NAME|mirror|raidz\d*|logs|cache|spares)$/i;
      next if $d eq $cur->{name};
      push @{ $cur->{devices} }, {name=>$d,state=>$st};
    }
  }
  return \@p;
}
sub zpool_properties {
  my ($pool,@props)=@_;
  return {} unless is_pool_name($pool);
  my @cmd=($ZPOOL,'get','-H','-o','property,value',(@props?join(',',@props):'all'),$pool);
  my ($rc,$out,$err)=run_cmd(@cmd);
  return {} if $rc!=0 || !$out;
  my %h;
  for my $ln (split /\n/,$out) { my ($k,$v)=split /\t+|\s+/,$ln,2; $h{$k}=defined($v)?$v:'' if defined $k; }
  return \%h;
}
sub zpool_set_property { my ($p,$k,$v)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'set',"$k=$v",$p); die $err if $rc!=0; 1; }
sub zpool_set_bootfs { my ($p,$d)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'set',"bootfs=$d",$p); die $err if $rc!=0; 1; }
sub zpool_create { my ($p,@v)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'create',$p,@v); die $err if $rc!=0; 1; }
sub zpool_rename {
  my ($o,$n)=@_;
  my ($rc,$out,$err)=run_cmd($ZPOOL,'rename',$o,$n);
  return 1 if $rc==0;

  my $msg = (defined($err) && $err ne '') ? $err : ($out // '');
  my $unsupported = 0;
  $unsupported = 1 if $msg =~ /(unrecognized|unknown|invalid)\s+command\s+'?rename'?/i;
  $unsupported = 1 if $msg =~ /\busage:\s*zpool\b/i && $msg !~ /\brename\b/i;
  if ($unsupported) {
    my ($erc,$eout,$eerr)=run_cmd($ZPOOL,'export',$o);
    if ($erc != 0) {
      my $export_msg = ($eerr && $eerr ne '') ? $eerr : ($eout // $msg);
      if ($export_msg =~ /(cannot\s+unmount|busy|resource\s+busy)/i) {
        my ($ferc,$fout,$ferr)=run_cmd($ZPOOL,'export','-f',$o);
        if ($ferc != 0) {
          my $force_msg = ($ferr && $ferr ne '') ? $ferr : ($fout // $export_msg);
          die($force_msg);
        }
      }
      else {
        die($export_msg);
      }
    }

    my ($irc,$iout,$ierr)=run_cmd($ZPOOL,'import',$o,$n);
    if ($irc != 0) {
      my $import_msg = ($ierr && $ierr ne '') ? $ierr : ($iout // 'zpool import failed');
      # Best-effort rollback so the original pool name is restored if rename import fails.
      my ($rrc,$rout,$rerr)=run_cmd($ZPOOL,'import',$o);
      if ($rrc != 0) {
        my $rollback_msg = ($rerr && $rerr ne '') ? $rerr : ($rout // 'rollback import failed');
        die($import_msg . "\nRollback failed: " . $rollback_msg);
      }
      die($import_msg);
    }
    return 1;
  }

  die($msg);
}
sub zpool_destroy { my ($p,@o)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'destroy',@o,$p); die $err if $rc!=0; 1; }
sub zpool_add { my ($p,@v)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'add',$p,@v); die $err if $rc!=0; 1; }
sub zpool_add_cache { my ($p,@d)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'add',$p,'cache',@d); die $err if $rc!=0; 1; }
sub zpool_add_log { my ($p,@d)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'add',$p,'log',@d); die $err if $rc!=0; 1; }
sub zpool_add_spare { my ($p,@d)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'add',$p,'spare',@d); die $err if $rc!=0; 1; }
sub zpool_replace { my ($p,$o,$n)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'replace',$p,$o,$n); die $err if $rc!=0; 1; }
sub zpool_remove { my ($p,$d)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'remove',$p,$d); die $err if $rc!=0; 1; }
sub zpool_scrub { my ($p,$m)=@_; my @cmd=($ZPOOL,'scrub'); push @cmd,'-s' if defined($m)&&$m eq 'stop'; push @cmd,$p; my ($rc,$out,$err)=run_cmd(@cmd); die $err if $rc!=0; 1; }
sub zpool_export { my ($p)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'export',$p); die $err if $rc!=0; 1; }
sub zpool_upgrade { my ($p)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'upgrade',$p); die $err if $rc!=0; 1; }
sub zpool_import {
  my (%o)=@_;
  my @cmd=($ZPOOL,'import');
  push @cmd,'-D' if $o{import_destroyed};
  push @cmd,'-f' if $o{force};
  my $devdir = $o{devdir};
  $devdir = $o{search_path} if !defined($devdir) || $devdir eq '';
  push @cmd,'-d',$devdir if defined($devdir) && $devdir ne '';
  push @cmd,$o{pool} if $o{pool};
  my ($rc,$out,$err)=run_cmd(@cmd); die $err if $rc!=0; 1;
}
sub zpool_import_list {
  my (%o)=@_;
  my @cmd=($ZPOOL,'import');
  push @cmd,'-D' if $o{import_destroyed};
  my $devdir = $o{devdir};
  $devdir = $o{search_path} if !defined($devdir) || $devdir eq '';
  push @cmd,'-d',$devdir if defined($devdir) && $devdir ne '';
  my ($rc,$out,$err)=run_cmd(@cmd); return [] if !defined($out) || $out !~ /\S/;
  my @rows; my $cur;
  for my $ln (split /\n/,$out) {
    if ($ln =~ /^\s*pool:\s*(\S+)/) { $cur={name=>$1}; push @rows,$cur; next; }
    next unless $cur;
    $cur->{id}=$1 if $ln =~ /^\s*id:\s*(\S+)/;
    $cur->{state}=$1 if $ln =~ /^\s*state:\s*(.+?)\s*$/;
    $cur->{status}=$1 if $ln =~ /^\s*status:\s*(.+)$/;
  }
  return \@rows;
}
sub zpool_history { my ($p,$lim)=@_; my ($rc,$out,$err)=run_cmd($ZPOOL,'history',$p); return [] if $rc!=0; my @l=grep{/\S/}split(/\n/,$out||''); if(defined($lim)&&$lim=~/^\d+$/&&@l>$lim){ @l=@l[@l-$lim..$#l]; } return \@l; }

sub zfs_list {
  my ($props,@extra)=@_;
  my @p=ref($props) eq 'ARRAY' ? @$props : qw(name used avail refer mountpoint);
  my ($rc,$out,$err)=run_cmd($ZFS,'list','-H','-o',join(',',@p),@extra);
  return [] if $rc!=0 || !$out;
  my @rows;
  for my $ln (split /\n/,$out) {
    next unless $ln =~ /\S/;
    my @v=split /\t+/,$ln,scalar(@p);
    @v=split /\s+/,$ln,scalar(@p) if @v<@p;
    my %h; for my $i (0..$#p) { $h{$p[$i]}=defined($v[$i])?$v[$i]:''; }
    push @rows,\%h;
  }
  return \@rows;
}
sub zfs_get { my ($d,@props)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'get','-H','-o','property,value',(@props?join(',',@props):'all'),$d); return {} if $rc!=0||!$out; my %h; for my $ln(split/\n/,$out){ my($k,$v)=split/\t+|\s+/,$ln,2; $h{$k}=defined($v)?$v:'' if defined $k; } return \%h; }
sub zfs_get_prop_value { my ($d,$p)=@_; my $h=zfs_get($d,$p); return ref($h) eq 'HASH' ? $h->{$p} : undef; }
sub zfs_get_prop_value_bytes { my ($d,$p)=@_; my $v=zfs_get_prop_value($d,$p); return undef unless defined $v; return $v+0 if $v =~ /^\d+$/; if($v =~ /^(\d+(?:\.\d+)?)([KMGTP])i?B?$/i){ my %m=(K=>1024,M=>1024**2,G=>1024**3,T=>1024**4,P=>1024**5); return int(($1+0)*$m{uc($2)}); } return undef; }
sub zfs_set { my ($d,$k,$v)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'set',"$k=$v",$d); die $err if $rc!=0; 1; }
sub zfs_create { my ($d,@o)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'create',@o,$d); die $err if $rc!=0; 1; }
sub zfs_create_volume { my ($d,$s,@o)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'create','-V',$s,@o,$d); die $err if $rc!=0; 1; }
sub zfs_resize_volume { my ($d,$s)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'set',"volsize=$s",$d); die $err if $rc!=0; 1; }
sub zfs_destroy { my ($t,@o)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'destroy',@o,$t); die $err if $rc!=0; 1; }
sub zfs_rename { my ($o,$n)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'rename',$o,$n); die $err if $rc!=0; 1; }
sub zfs_inherit { my ($d,$k)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'inherit',$k,$d); die $err if $rc!=0; 1; }
sub zfs_snapshot { my ($s,@o)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'snapshot',@o,$s); die $err if $rc!=0; 1; }
sub zfs_list_snapshots { my ($d)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'list','-H','-t','snapshot','-o','name,used,creation','-s','creation','-r',$d); return [] if $rc!=0||!$out; my @r; for my $ln(split/\n/,$out){ my($n,$u,$c)=split/\t+|\s+/,$ln,3; push @r,{name=>$n,used=>$u,creation=>$c} if $n; } return \@r; }
sub zfs_list_snapshots_all { my ($rc,$out,$err)=run_cmd($ZFS,'list','-H','-t','snapshot','-o','name,used,creation','-s','creation'); return [] if $rc!=0||!$out; my @r; for my $ln(split/\n/,$out){ my($n,$u,$c)=split/\t+|\s+/,$ln,3; push @r,{name=>$n,used=>$u,creation=>$c} if $n; } return \@r; }
sub zfs_destroy_snapshot { my ($s)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'destroy',$s); die $err if $rc!=0; 1; }
sub zfs_rollback {
  my ($s,$opt)=@_;
  my @cmd = ($ZFS,'rollback');
  if (ref($opt) eq 'HASH') {
    push @cmd, '-r' if $opt->{destroy_newer};
    push @cmd, '-R' if $opt->{destroy_clones};
    push @cmd, '-f' if $opt->{force};
  }
  else {
    # Backward-compatible default for older callsites.
    push @cmd, '-r';
  }
  push @cmd, $s;
  my ($rc,$out,$err)=run_cmd(@cmd);
  die $err if $rc!=0;
  1;
}
sub zfs_promote { my ($d)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'promote',$d); die $err if $rc!=0; 1; }
sub zfs_clone { my ($s,$t)=@_; my ($rc,$out,$err)=run_cmd($ZFS,'clone',$s,$t); die $err if $rc!=0; 1; }
sub zfs_send_incremental { my ($f,$t,$d)=@_; my ($rc,$out,$err)=run_cmd('/bin/sh','-c',_cmdstr($ZFS,'send','-i',$f,$t).' | '._cmdstr($ZFS,'receive','-F',$d)); die $err if $rc!=0; 1; }
sub zfs_receive { my ($d,$f)=@_; my ($rc,$out,$err)=run_cmd('/bin/sh','-c',_cmdstr($ZFS,'receive','-F',$d).' < '._q($f)); die $err if $rc!=0; 1; }
sub zfs_set_quota { zfs_set($_[0],'quota',$_[1]); }
sub zfs_set_reservation { zfs_set($_[0],'reservation',$_[1]); }
sub zfs_set_refquota { zfs_set($_[0],'refquota',$_[1]); }
sub zfs_version { my ($rc,$out,$err)=run_cmd($ZFS,'version'); if($rc==0 && $out =~ /\S/){ my ($l)=grep{/\S/}split(/\n/,$out); return $l; } return undef; }
sub zfs_pool_version { my ($pool)=@_; my $p=zpool_properties($pool,'version'); return $p->{version}; }
sub zfs_features { my ($pool)=@_; my $p=zpool_properties($pool); my %f; for my $k(keys %$p){ $f{$1}=$p->{$k} if $k =~ /^feature\@(.+)$/; } return \%f; }

# system/disk/network -----------------------------------------------------
sub disk_list { my ($rc,$out,$err)=run_cmd($SYSCTL,'-n','kern.disks'); my @d=($rc==0&&$out)?grep{/^[A-Za-z][A-Za-z0-9_.:\-]*$/}split(/\s+/,$out):(); return \@d; }
sub diskinfo {
  my ($d)=@_;
  return undef unless is_disk_name($d);
  my $dev=$d =~ m{^/dev/}?$d:"/dev/$d";
  my ($rc,$out,$err)=run_cmd($DISKINFO,$dev);
  return undef if $rc!=0 || !$out || $out!~/\S/;

  my @p = split(/\s+/, $out);
  return undef if @p < 3 || $p[1] !~ /^\d+$/ || $p[2] !~ /^\d+$/;

  # FreeBSD diskinfo generally prints: <name> <sectorsize> <mediasize> ...
  # Keep backward compatibility if order appears reversed.
  my ($a,$b) = ($p[1]+0, $p[2]+0);
  my ($ss,$ms);
  if ($a > 0 && $a <= 65536 && $b > $a) {
    $ss = $a; $ms = $b;
  } else {
    $ms = $a; $ss = $b;
  }

  my $stripesize   = (defined $p[3] && $p[3] =~ /^\d+$/) ? ($p[3]+0) : undef;
  my $stripeoffset = (defined $p[4] && $p[4] =~ /^\d+$/) ? ($p[4]+0) : undef;

  return {
    name         => $d,
    mediasize    => $ms,
    sectorsize   => $ss,
    sectorcount  => ($ss ? int($ms/$ss) : 0),
    stripesize   => $stripesize,
    stripeoffset => $stripeoffset,
    raw          => $out,
  };
}
sub camcontrol_identify_raw { my ($rc,$out,$err)=run_cmd($CAMCONTROL,'identify',$_[0]); return $rc==0?($out||''):''; }
my $_CAMCONTROL_DEVLIST_V_CACHE;
sub camcontrol_devlist_v_raw {
  return $_CAMCONTROL_DEVLIST_V_CACHE if defined $_CAMCONTROL_DEVLIST_V_CACHE;
  my ($rc,$out,$err)=run_cmd($CAMCONTROL,'devlist','-v');
  $_CAMCONTROL_DEVLIST_V_CACHE = ($rc==0 && defined $out) ? $out : '';
  return $_CAMCONTROL_DEVLIST_V_CACHE;
}
sub camcontrol_disk_bus_hint {
  my ($disk)=@_;
  return '' unless defined $disk && $disk ne '';
  my $d = $disk; $d =~ s{^/dev/}{};
  my $raw = camcontrol_devlist_v_raw();
  return '' unless defined $raw && $raw ne '';
  my $cur_bus = '';
  for my $ln (split /\n/, $raw) {
    if ($ln =~ /^scbus\d+\s+on\s+(.+?)\s+bus\s+\d+:/i) {
      $cur_bus = lc($1 || '');
      next;
    }
    next unless $cur_bus ne '';
    if ($ln =~ /\(([^)]*)\)/) {
      my $inside = $1 || '';
      my @devs = map { s/^\s+|\s+$//gr } split /,/, $inside;
      for my $dev (@devs) {
        next unless $dev ne '' && $dev ne 'xpt0' && $dev ne 'pass';
        return $cur_bus if lc($dev) eq lc($d);
      }
    }
  }
  return '';
}
sub disk_identify { return { raw => camcontrol_identify_raw($_[0]) }; }
sub disk_detect_type {
  my ($disk, $hint_text) = @_;
  $disk = '' unless defined $disk;
  $hint_text = '' unless defined $hint_text;
  my $d = lc($disk);
  my $hint = lc($hint_text);
  my $bus_hint = lc(camcontrol_disk_bus_hint($disk) || '');
  $hint .= " $bus_hint" if $bus_hint ne '';

  return 'memdisk' if $d =~ /^md\d+$/;
  return 'nvme'    if $d =~ /^(?:nvme|nvd|nda)\d+/;

  # USB-attached storage often appears as daX on FreeBSD.
  # Keep detection based on generic bus/protocol terms only.
  if ($hint =~ /\b(?:usb|umass|uas|mass\s+storage)\b/) {
    return 'usbstick';
  }
  if ($hint =~ /\b(?:nvme|pcie ssd|m\.2)\b/) {
    return 'ssd';
  }
  if ($hint =~ /\b(?:ssd|solid state|non-rotat)\b/) {
    return 'ssd';
  }
  if ($hint =~ /\b(?:hdd|hard disk|rotation rate|rpm)\b/) {
    return 'hdd';
  }
  # Common rotating-disk model families seen in hint text.
  if ($hint =~ /\b(?:st\d{5,}|wdc?\s*wd|toshiba|hitachi|hgst)\b/) {
    return 'hdd';
  }

  my $raw = lc(camcontrol_identify_raw($disk) || '');
  if ($raw ne '') {
    return 'ssd' if $raw =~ /solid state|non-rotat|\bssd\b/;
    return 'hdd' if $raw =~ /rotation rate|rpm/;
  }

  # Default class for remaining block disks.
  return 'hdd' if $d =~ /^(?:ada|da)\d+$/;
  return 'disk';
}
sub disk_power_state {
  my ($disk) = @_;
  my ($rc, $out, $err) = run_cmd($CAMCONTROL, 'powermode', $disk);
  my $txt = join(' ', grep { defined($_) && length($_) } ($out, $err));
  my $lc = lc($txt || '');

  # USB/bridge devices often do not support this query; report unknown instead
  # of incorrectly mapping to sleeping.
  return 'unknown' if $rc != 0 || $lc eq '';
  return 'sleeping' if $lc =~ /standby|sleep/;
  return 'ready' if $lc =~ /active|idle|ready|run/;
  return 'unknown';
}
sub disk_is_spinning { return disk_power_state($_[0]) eq 'ready' ? 1 : 0; }
sub disk_spindown { my ($rc,$out,$err)=run_cmd($CAMCONTROL,'standby',$_[0]); return ($rc==0,$err||$out); }
sub disk_spinup { my ($rc,$out,$err)=run_cmd($CAMCONTROL,'start',$_[0]); return ($rc==0,$err||$out); }
sub disk_set_apm { my ($rc,$out,$err)=run_cmd($CAMCONTROL,'apm',$_[0],'-l',$_[1]); return ($rc==0,$err||$out); }
sub _dd_end_of_device_ok {
  my ($txt)=@_;
  $txt='' unless defined $txt;
  my $lc = lc($txt);
  return 0 unless $lc =~ /end of device/;
  return 1 if $lc =~ /short write on character device/;
  return 0;
}
sub disk_zero_write {
  my ($rc,$out,$err)=run_cmd($DD,'if=/dev/zero',"of=$_[0]",'bs=1m');
  my $txt = join("\n", grep { defined($_) && length($_) } ($out,$err));
  return (1,$txt) if $rc!=0 && _dd_end_of_device_ok($txt);
  return ($rc==0,$err||$out);
}
sub disk_random_write {
  my ($rc,$out,$err)=run_cmd($DD,'if=/dev/random',"of=$_[0]",'bs=1m');
  my $txt = join("\n", grep { defined($_) && length($_) } ($out,$err));
  return (1,$txt) if $rc!=0 && _dd_end_of_device_ok($txt);
  return ($rc==0,$err||$out);
}
sub disk_secure_erase { my ($rc,$out,$err)=run_cmd($CAMCONTROL,'sanitize',$_[0],'-a','block','-y'); return ($rc==0,$err||$out); }
sub disk_blkdiscard { return (0,'blkdiscard unavailable') unless command_exists($BLKDISCARD); my ($rc,$out,$err)=run_cmd($BLKDISCARD,$_[0]); return ($rc==0,$err||$out); }
sub ata_secure_erase_available {
  my $cmd = $ATA_SECURE_ERASE || '';
  return (0, 'ata secure erase wrapper command is not configured') unless $cmd ne '';
  return (0, "ata secure erase wrapper command is not executable: $cmd") unless command_exists($cmd);
  my @a = shellwords($ATA_SECURE_ERASE_ARGS || '');
  if (@a) {
    my $first = $a[0];
    my $resolved = _resolve_module_path($first);
    if ($first =~ m{^/} || $first =~ m{^\./} || $first =~ m{^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]}) {
      $a[0] = $resolved;
    }
    return (0, "ata secure erase wrapper script is not readable: $a[0]") unless -r $a[0];
  }
  return (1, '');
}
sub disk_ata_secure_erase {
  my ($ok,$why)=ata_secure_erase_available();
  return (0, $why || 'ata secure erase wrapper not configured') unless $ok;
  my @a = shellwords($ATA_SECURE_ERASE_ARGS || '');
  if (@a) {
    my $first = $a[0];
    if ($first =~ m{^/} || $first =~ m{^\./} || $first =~ m{^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]}) {
      $a[0] = _resolve_module_path($first);
    }
  }
  local $ENV{'ZFSGURU_ATA_PASS'} = $ATA_SECURE_ERASE_PASS if defined $ATA_SECURE_ERASE_PASS;
  local $ENV{'ZFSGURU_ATA_MODE'} = $ATA_SECURE_ERASE_MODE if defined $ATA_SECURE_ERASE_MODE;
  my ($rc,$out,$err)=run_cmd($ATA_SECURE_ERASE,@a,$_[0]);
  return ($rc==0,$err||$out);
}
sub disk_wipe_head { my ($dev,$m)=@_; $m=16 unless defined($m)&&$m=~/^\d+$/&&$m>0; my ($rc,$out,$err)=run_cmd($DD,'if=/dev/zero',"of=$dev",'bs=1m',"count=$m"); return ($rc==0,$err||$out); }
sub disk_dmesg_map { my ($disks)=@_; my %m; my ($rc,$out,$err)=run_cmd('dmesg'); return \%m if $rc!=0||!$out; for my $d(@{$disks||[]}){ $m{$d}=$1 if $out =~ /\b\Q$d\E:\s+<([^>]+)>/m; } return \%m; }
sub disk_geom_labels_map { my %m; my ($rc,$out,$err)=run_cmd($GLABEL,'status'); return \%m if $rc!=0||!$out; for my $ln(split/\n/,$out){ next if $ln =~ /^\s*Name\s+Status/i; my($n,$s,$p)=split(/\s+/,$ln,3); next unless $n&&$p; $p =~ s{^/dev/}{}; push @{ $m{$p} },$n; } return \%m; }
sub _gpart_list_providers {
  my ($d)=@_;
  $d = '' unless defined $d;
  $d =~ s{^/dev/}{};
  return [] unless is_disk_name($d);
  my ($rc,$out,$err)=run_cmd($GPART,'list',$d);
  return [] if $rc!=0 || !$out;
  my @p; my $cur;
  for my $ln (split /\n/, $out) {
    if ($ln =~ /^\s*Consumers:\s*$/) {
      push @p, $cur if $cur && $cur->{name};
      $cur = undef;
      next;
    }
    if ($ln =~ /^\s*\d+\.\s+Name:\s+(\S+)/) {
      push @p, $cur if $cur && $cur->{name};
      $cur = { name => $1 };
      next;
    }
    next unless $cur;
    if ($ln =~ /^\s*label:\s*(.+?)\s*$/i)      { $cur->{label} = $1; next; }
    if ($ln =~ /^\s*type:\s*(.+?)\s*$/i)       { $cur->{type} = $1; next; }
    if ($ln =~ /^\s*rawtype:\s*(.+?)\s*$/i)    { $cur->{rawtype} = $1; next; }
    if ($ln =~ /^\s*rawuuid:\s*(.+?)\s*$/i)    { $cur->{rawuuid} = $1; next; }
    if ($ln =~ /^\s*uuid:\s*(.+?)\s*$/i)       { $cur->{uuid} = $1; next; }
    if ($ln =~ /^\s*index:\s*(\d+)\s*$/i)      { $cur->{index} = int($1); next; }
    if ($ln =~ /^\s*start:\s*(\d+)\s*$/i)      { $cur->{start} = int($1); next; }
    if ($ln =~ /^\s*end:\s*(\d+)\s*$/i)        { $cur->{end} = int($1); next; }
    if ($ln =~ /^\s*length:\s*(\d+)\s*$/i)     { $cur->{length_bytes} = int($1); next; }
    if ($ln =~ /^\s*offset:\s*(\d+)\s*$/i)     { $cur->{offset_bytes} = int($1); next; }
    if ($ln =~ /^\s*Sectorsize:\s*(\d+)\s*$/i) { $cur->{sectorsize} = int($1); next; }
  }
  push @p, $cur if $cur && $cur->{name};
  return \@p;
}
sub disk_gpt_labels_map {
  my ($disks)=@_;
  my %m;
  for my $raw (@{$disks||[]}) {
    my $d = defined($raw) ? $raw : '';
    $d =~ s{^/dev/}{};
    next unless is_disk_name($d);
    my $pl = _gpart_list_providers($d);
    if ($pl && @$pl) {
      for my $pp (@$pl) {
        next unless ref($pp) eq 'HASH';
        my $name = $pp->{name} || '';
        next unless $name =~ /^\Q$d\E(?:p|s)\d+$/;
        my $label = $pp->{label} || '';
        next unless $label ne '';
        push @{ $m{$d} }, $label;
      }
      my %seen;
      @{ $m{$d} } = grep { defined($_) && $_ ne '' && !$seen{$_}++ } @{ $m{$d} || [] };
      next;
    }
    my ($rc,$out,$err)=run_cmd($GPART,'show','-l',$d);
    next if $rc!=0||!$out;
    while($out =~ /\b([A-Za-z0-9_.\-]+)\s*$/mg){ push @{ $m{$d} },$1; }
  }
  return \%m;
}
sub disk_partition_map {
  my ($d)=@_;
  $d = '' unless defined $d;
  $d =~ s{^/dev/}{};
  return [] unless is_disk_name($d);

  my $pl = _gpart_list_providers($d);
  if ($pl && @$pl) {
    my @r;
    for my $pp (@$pl) {
      next unless ref($pp) eq 'HASH';
      my $name = $pp->{name} || '';
      next unless $name =~ /^\Q$d\E(?:p|s)\d+$/;
      my $idx = defined($pp->{index}) ? int($pp->{index}) : undef;
      my $start = defined($pp->{start}) ? int($pp->{start}) : undef;
      my $end = defined($pp->{end}) ? int($pp->{end}) : undef;
      my $ss = defined($pp->{sectorsize}) ? int($pp->{sectorsize}) : 0;
      my $sz;
      if (defined($pp->{length_bytes}) && $ss > 0) {
        $sz = int($pp->{length_bytes} / $ss);
      } elsif (defined($start) && defined($end) && $end >= $start) {
        $sz = ($end - $start + 1);
      }
      push @r, {
        name  => $name,
        index => $idx,
        type  => ($pp->{type} || ''),
        rawtype => ($pp->{rawtype} || ''),
        rawuuid => ($pp->{rawuuid} || $pp->{uuid} || ''),
        label => ($pp->{label} || ''),
        start => $start,
        end   => $end,
        size  => $sz,
      };
    }
    return \@r;
  }

  my ($rc,$out,$err)=run_cmd($GPART,'show','-p',$d);
  return [] if $rc!=0||!$out;
  my @r;
  for my $ln(split/\n/,$out){
    if($ln =~ /^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)/){
      push @r,{
        start=>$1+0,size=>$2+0,index=>$3+0,type=>$4,
        name=>$d.'p'.$3,end=>($1+$2-1)
      };
    }
  }
  return \@r;
}
sub bootcode_paths {
  my $mdir = ($module_root_directory || $LIBDIR).'/bootcode';
  return {
    module_bootcode_dir  => $mdir,
    system_boot_dir      => '/boot',
    pmbr                 => "$mdir/pmbr",
    gptzfsboot           => "$mdir/gptzfsboot",
    gptboot              => "$mdir/gptboot",
    system_pmbr          => '/boot/pmbr',
    system_gptzfsboot    => '/boot/gptzfsboot',
    system_gptboot       => '/boot/gptboot',
  };
}

sub _sha256_stream_from_fh {
  my ($fh, $want_bytes) = @_;
  return undef unless $fh;
  my $sha = Digest::SHA->new(256);
  my $left = (defined($want_bytes) && $want_bytes =~ /^\d+$/) ? int($want_bytes) : -1;
  my $read_total = 0;
  my $buf = '';
  while (1) {
    my $to_read = ($left >= 0 && $left < 65536) ? $left : 65536;
    last if $left == 0;
    my $n = read($fh, $buf, $to_read);
    return undef unless defined $n;
    last if $n == 0;
    $read_total += $n;
    $sha->add(substr($buf, 0, $n));
    $left -= $n if $left >= 0;
  }
  return undef if $read_total <= 0;
  return $sha->hexdigest;
}

sub _sha256_of_file {
  my ($path,$bytes)=@_;
  return undef unless defined $path && -r $path;
  open my $fh, '<', $path or return undef;
  binmode($fh);
  my $hash = _sha256_stream_from_fh($fh, $bytes);
  close $fh;
  return $hash;
}

sub _sha256_of_dev {
  my ($dev,$bytes)=@_;
  return undef unless defined $dev && $dev =~ m{^/dev/};
  open my $fh, '<', $dev or return undef;
  binmode($fh);
  my $hash = _sha256_stream_from_fh($fh, $bytes);
  close $fh;
  return $hash;
}

sub _sha256_of_file_range {
  my ($path,$skip,$bytes)=@_;
  return undef unless defined $path && -r $path;
  $skip = 0 unless defined($skip) && $skip =~ /^\d+$/;
  open my $fh, '<', $path or return undef;
  binmode($fh);
  if ($skip > 0) {
    my $ok = seek($fh, $skip, 0);
    if (!$ok) { close $fh; return undef; }
  }
  my $hash = _sha256_stream_from_fh($fh, $bytes);
  close $fh;
  return $hash;
}

sub _sha256_of_dev_range {
  my ($dev,$skip,$bytes)=@_;
  return undef unless defined $dev && $dev =~ m{^/dev/};
  $skip = 0 unless defined($skip) && $skip =~ /^\d+$/;
  open my $fh, '<', $dev or return undef;
  binmode($fh);
  if ($skip > 0) {
    my $ok = seek($fh, $skip, 0);
    if (!$ok) { close $fh; return undef; }
  }
  my $hash = _sha256_stream_from_fh($fh, $bytes);
  close $fh;
  return $hash;
}

sub _sig_string {
  my ($path,$bytes)=@_;
  return '-' unless defined $path && -r $path;
  my $sz = (stat($path))[7];
  my $hash = _sha256_of_file($path,$bytes);
  return '-' unless defined $hash && $hash ne '';
  return (defined($sz) ? $sz : '?').':'.$hash;
}

sub gpt_bootcode_status {
  my ($disk,$boot_part_dev)=@_;
  my %rv = (
    state                         => 'unknown',
    error                         => '',
    detected_bootcode             => '',
    boot_part_bytes               => undef,
    actual_mbr                    => '-',
    expected_mbr                  => '-',
    system_mbr                    => '-',
    actual_bootcode_gptzfsboot    => '-',
    expected_bootcode_gptzfsboot  => '-',
    system_bootcode_gptzfsboot    => '-',
    actual_bootcode_gptboot       => '-',
    expected_bootcode_gptboot     => '-',
    system_bootcode_gptboot       => '-',
  );

  $disk='' unless defined $disk;
  $disk =~ s{^/dev/}{};
  return { %rv, state => 'error', error => 'Invalid disk' } unless is_disk_name($disk);
  my $disk_dev = "/dev/$disk";

  my $paths = bootcode_paths();
  my $part_dev = $boot_part_dev || '';
  if ($part_dev !~ m{^/dev/}) {
    my $plist = disk_partition_map($disk) || [];
    for my $p (@$plist) {
      next unless ref($p) eq 'HASH';
      next unless ($p->{type}||'') eq 'freebsd-boot';
      my $n = $p->{name} || '';
      next unless $n ne '';
      $part_dev = "/dev/$n";
      $rv{boot_part_bytes} = $p->{length_bytes} if defined $p->{length_bytes};
      last;
    }
  }
  if ($part_dev =~ m{^/dev/} && !defined($rv{boot_part_bytes})) {
    my $pd = $part_dev; $pd =~ s{^/dev/}{};
    my $plist = disk_partition_map($disk) || [];
    for my $p (@$plist) {
      next unless ref($p) eq 'HASH';
      next unless ($p->{name}||'') eq $pd;
      $rv{boot_part_bytes} = $p->{length_bytes} if defined $p->{length_bytes};
      last;
    }
  }

  my $mbr_bytes = 440;
  my $pmbr_mod = $paths->{pmbr};
  my $pmbr_sys = $paths->{system_pmbr};
  $rv{expected_mbr} = _sig_string($pmbr_mod,$mbr_bytes) if $pmbr_mod;
  $rv{system_mbr}   = _sig_string($pmbr_sys,$mbr_bytes) if $pmbr_sys;
  my $ambr = _sha256_of_dev($disk_dev,$mbr_bytes);
  $rv{actual_mbr} = ($ambr && $ambr ne '') ? ($mbr_bytes.':'.$ambr) : '-';

  my $zfs_mod = $paths->{gptzfsboot};
  my $zfs_sys = $paths->{system_gptzfsboot};
  my $ufs_mod = $paths->{gptboot};
  my $ufs_sys = $paths->{system_gptboot};
  $rv{expected_bootcode_gptzfsboot} = _sig_string($zfs_mod,undef) if $zfs_mod;
  $rv{system_bootcode_gptzfsboot}   = _sig_string($zfs_sys,undef) if $zfs_sys;
  $rv{expected_bootcode_gptboot}    = _sig_string($ufs_mod,undef) if $ufs_mod;
  $rv{system_bootcode_gptboot}      = _sig_string($ufs_sys,undef) if $ufs_sys;

  if ($part_dev !~ m{^/dev/}) {
    $rv{state} = 'unknown';
    $rv{error} = 'No freebsd-boot partition selected/found';
    return \%rv;
  }

  my $zfs_len = (defined($zfs_mod) && -r $zfs_mod) ? (stat($zfs_mod))[7] : ((defined($zfs_sys) && -r $zfs_sys) ? (stat($zfs_sys))[7] : undef);
  my $ufs_len = (defined($ufs_mod) && -r $ufs_mod) ? (stat($ufs_mod))[7] : ((defined($ufs_sys) && -r $ufs_sys) ? (stat($ufs_sys))[7] : undef);
  my $max_len = 0;
  $max_len = $zfs_len if defined($zfs_len) && $zfs_len > $max_len;
  $max_len = $ufs_len if defined($ufs_len) && $ufs_len > $max_len;
  $max_len = 262144 if !$max_len;

  my $apart = _sha256_of_dev($part_dev,$max_len);
  if (!$apart) {
    $rv{state} = 'error';
    $rv{error} = 'Unable to read boot partition bytes';
    return \%rv;
  }

  my $azfs = defined($zfs_len) ? _sha256_of_dev($part_dev,$zfs_len) : undef;
  my $aufs = defined($ufs_len) ? _sha256_of_dev($part_dev,$ufs_len) : undef;
  $rv{actual_bootcode_gptzfsboot} = (defined($azfs) && $azfs ne '' && defined($zfs_len)) ? ($zfs_len.':'.$azfs) : '-';
  $rv{actual_bootcode_gptboot}    = (defined($aufs) && $aufs ne '' && defined($ufs_len)) ? ($ufs_len.':'.$aufs) : '-';

  my @zfs_expected = grep { defined $_ && $_ ne '-' } ($rv{expected_bootcode_gptzfsboot}, $rv{system_bootcode_gptzfsboot});
  my @ufs_expected = grep { defined $_ && $_ ne '-' } ($rv{expected_bootcode_gptboot}, $rv{system_bootcode_gptboot});
  my $zfs_match = 0;
  my $ufs_match = 0;
  if (defined($azfs) && defined($zfs_len)) {
    my $got = $zfs_len.':'.$azfs;
    $zfs_match = scalar grep { $_ eq $got } @zfs_expected;
  }
  if (defined($aufs) && defined($ufs_len)) {
    my $got = $ufs_len.':'.$aufs;
    $ufs_match = scalar grep { $_ eq $got } @ufs_expected;
  }
  # Some environments may patch the first sector when installing bootcode.
  # Accept a tail match (skip first 512 bytes) as valid.
  if (!$zfs_match && defined($zfs_len) && $zfs_len > 512) {
    my $got_tail = _sha256_of_dev_range($part_dev, 512, $zfs_len - 512);
    if (defined($got_tail) && $got_tail ne '') {
      my @exp_tail;
      for my $p ($zfs_mod, $zfs_sys) {
        next unless defined($p) && -r $p;
        my $h = _sha256_of_file_range($p, 512, $zfs_len - 512);
        push @exp_tail, $h if defined($h) && $h ne '';
      }
      my %seen;
      @exp_tail = grep { !$seen{$_}++ } @exp_tail;
      $zfs_match = scalar(grep { $_ eq $got_tail } @exp_tail) ? 1 : 0;
    }
  }
  if (!$ufs_match && defined($ufs_len) && $ufs_len > 512) {
    my $got_tail = _sha256_of_dev_range($part_dev, 512, $ufs_len - 512);
    if (defined($got_tail) && $got_tail ne '') {
      my @exp_tail;
      for my $p ($ufs_mod, $ufs_sys) {
        next unless defined($p) && -r $p;
        my $h = _sha256_of_file_range($p, 512, $ufs_len - 512);
        push @exp_tail, $h if defined($h) && $h ne '';
      }
      my %seen;
      @exp_tail = grep { !$seen{$_}++ } @exp_tail;
      $ufs_match = scalar(grep { $_ eq $got_tail } @exp_tail) ? 1 : 0;
    }
  }
  if ($zfs_match && !$ufs_match) {
    $rv{detected_bootcode} = 'gptzfsboot';
    $rv{state} = 'ok';
  } elsif ($ufs_match && !$zfs_match) {
    $rv{detected_bootcode} = 'gptboot';
    $rv{state} = 'ok';
  } elsif ($zfs_match && $ufs_match) {
    $rv{state} = 'ok';
  } else {
    $rv{state} = 'old';
  }

  return \%rv;
}
sub gpart_list_partitions_info { return disk_partition_map($_[0]); }
sub gpart_supports_subcommand { my ($s)=@_; my ($rc,$out,$err)=run_cmd($GPART,'help'); return ($rc==0 && $out =~ /\b\Q$s\E\b/) ? 1 : 0; }
sub device_mountpoints { my ($d)=@_; return [] unless defined $d; $d =~ s{^/dev/}{}; my ($rc,$out,$err)=run_cmd($MOUNT); return [] if $rc!=0||!$out; my @m; for my $ln(split/\n/,$out){ push @m,$1 if $ln =~ m{^/dev/\Q$d\E\s+on\s+(\S+)\s+}; } return \@m; }
sub device_in_zpool {
  my ($d)=@_;
  return undef unless defined $d;
  $d =~ s{^/dev/}{};
  return undef unless length $d;
  my $st = zpool_status();
  return undef unless defined($st) && $st =~ /\S/;
  my %pools;
  my $cur = '';
  for my $ln (split /\n/, $st) {
    if ($ln =~ /^\s*pool:\s*(\S+)/) {
      $cur = $1;
      next;
    }
    next unless $cur ne '';
    if ($ln =~ /^\s+(\S+)\s+(ONLINE|OFFLINE|DEGRADED|FAULTED|UNAVAIL|REMOVED|AVAIL|INUSE)/i) {
      my $dev = $1;
      next if $dev eq $cur;
      $dev =~ s{^/dev/}{};
      if ($dev eq $d || $dev =~ m{^(?:gpt|label)/\Q$d\E$}) {
        $pools{$cur} = 1;
      }
    }
  }
  my @list = sort keys %pools;
  return @list ? \@list : undef;
}
sub gpart_show { my ($rc,$out,$err)=run_cmd($GPART,'show',$_[0]); return $rc==0?($out||''):''; }
sub glabel_list { my ($rc,$out,$err)=run_cmd($GLABEL,'status'); return [] if $rc!=0||!$out; my @r; for my $ln(split/\n/,$out){ next if $ln =~ /^\s*Name\s+Status/i; my($n,$s,$p)=split(/\s+/,$ln,3); push @r,{name=>$n,status=>$s,provider=>$p} if $n&&$p; } return \@r; }
sub glabel_create { my ($rc,$out,$err)=run_cmd($GLABEL,'create',$_[0],$_[1]); die $err if $rc!=0; 1; }
sub glabel_destroy { my ($rc,$out,$err)=run_cmd($GLABEL,'destroy',$_[0]); die $err if $rc!=0; 1; }
my %_SMART_DEVINFO_CACHE;
sub _smartctl_text {
  my ($out, $err) = @_;
  return join("\n", grep { defined($_) && length($_) } ($out, $err));
}
sub _smartctl_needs_devtype {
  my ($txt) = @_;
  $txt = '' unless defined $txt;
  return ($txt =~ /please specify device type with the -d option/i ||
          $txt =~ /unknown usb bridge/i) ? 1 : 0;
}
sub _smartctl_backend_label {
  my ($cand) = @_;
  return 'direct' unless ref($cand) eq 'ARRAY' && @$cand >= 2;
  return $cand->[1] || 'direct';
}
sub _smartctl_plan_for_hint {
  my ($hint) = @_;
  $hint = lc($hint || '');
  my @plan;
  if ($hint =~ /(?:usb bridge|unknown usb bridge|\busb\b|\bumass\b|\buas\b)/) {
    # Bridge-specific preferred order for better USB SMART compatibility.
    if ($hint =~ /(?:jmicron|\bjms\d*\b|0x152d:)/) {
      @plan = (
        ['-d', 'sat,12'],
        ['-d', 'sat,16'],
        ['-d', 'sat'],
        ['-d', 'scsi'],
        ['-d', 'auto'],
      );
    } elsif ($hint =~ /(?:asmedia|\basm\d*\b|0x174c:)/) {
      @plan = (
        ['-d', 'sat'],
        ['-d', 'sat,12'],
        ['-d', 'sat,16'],
        ['-d', 'scsi'],
        ['-d', 'auto'],
      );
    } else {
      @plan = (
        ['-d', 'sat'],
        ['-d', 'scsi'],
        ['-d', 'sat,12'],
        ['-d', 'sat,16'],
        ['-d', 'auto'],
      );
    }
  } else {
    @plan = (
      [],
      ['-d', 'auto'],
      ['-d', 'sat'],
      ['-d', 'scsi'],
    );
  }
  return \@plan;
}
sub smartctl_detect_devarg {
  my ($disk) = @_;
  return [] unless defined $disk && length $disk;
  if (exists $_SMART_DEVINFO_CACHE{$disk} && ref($_SMART_DEVINFO_CACHE{$disk}) eq 'HASH') {
    return $_SMART_DEVINFO_CACHE{$disk}{args} || [];
  }

  my $dev = ($disk =~ m{^/dev/}) ? $disk : "/dev/$disk";
  my $best = [];
  my ($prc, $pout, $perr) = run_cmd($SMARTCTL, '-i', $dev);
  my $probe_txt = _smartctl_text($pout, $perr);
  my $plan = _smartctl_plan_for_hint($probe_txt);

  for my $cand (@$plan) {
    my ($rc, $out, $err) = run_cmd($SMARTCTL, @$cand, '-i', $dev);
    my $txt = _smartctl_text($out, $err);
    next if _smartctl_needs_devtype($txt);
    if ($rc == 0 || $txt =~ /SMART support is:|Serial Number:|Model Number:|Device Model:/i) {
      $best = $cand;
      last;
    }
  }
  $_SMART_DEVINFO_CACHE{$disk} = {
    args  => $best,
    label => _smartctl_backend_label($best),
    probe => $probe_txt,
  };
  return $best;
}
sub smart_detected_backend {
  my ($disk) = @_;
  smartctl_detect_devarg($disk);
  my $info = $_SMART_DEVINFO_CACHE{$disk};
  return 'direct' unless ref($info) eq 'HASH';
  return $info->{label} || 'direct';
}
sub smart_info {
  my ($disk) = @_;
  my $dev = ($disk =~ m{^/dev/}) ? $disk : "/dev/$disk";
  my $devarg = smartctl_detect_devarg($disk);
  my ($rc, $out, $err) = run_cmd($SMARTCTL, @$devarg, '-a', $dev);
  my $txt = _smartctl_text($out, $err);
  if ($rc != 0 && _smartctl_needs_devtype($txt) && !@$devarg) {
    for my $cand (_smartctl_devarg_candidates()) {
      next unless @$cand;
      my ($trc, $tout, $terr) = run_cmd($SMARTCTL, @$cand, '-a', $dev);
      my $ttxt = _smartctl_text($tout, $terr);
      next if _smartctl_needs_devtype($ttxt);
      $_SMART_DEVINFO_CACHE{$disk} = {
        args  => $cand,
        label => _smartctl_backend_label($cand),
      };
      return $ttxt if $ttxt ne '';
      last if $trc == 0;
    }
  }
  return $txt;
}
sub smart_enable {
  my ($disk) = @_;
  my $dev = ($disk =~ m{^/dev/}) ? $disk : "/dev/$disk";
  my $devarg = smartctl_detect_devarg($disk);
  my ($rc, $out, $err) = run_cmd($SMARTCTL, @$devarg, '-s', 'on', $dev);
  my $txt = _smartctl_text($out, $err);
  if ($rc != 0 && _smartctl_needs_devtype($txt) && !@$devarg) {
    for my $cand (_smartctl_devarg_candidates()) {
      next unless @$cand;
      my ($trc, $tout, $terr) = run_cmd($SMARTCTL, @$cand, '-s', 'on', $dev);
      my $ttxt = _smartctl_text($tout, $terr);
      next if _smartctl_needs_devtype($ttxt);
      $_SMART_DEVINFO_CACHE{$disk} = {
        args  => $cand,
        label => _smartctl_backend_label($cand),
      };
      return ($trc == 0, $ttxt);
    }
  }
  return ($rc == 0, $txt);
}
sub gpart_restore { my ($rc,$out,$err)=run_cmd_input($_[1],$GPART,'restore',$_[0]); die $err if $rc!=0; 1; }
sub swapctl_list { my ($rc,$out,$err)=run_cmd($SWAPCTL,'-l'); return [] if $rc!=0||!$out; my @r; for my $ln(split/\n/,$out){ next if $ln =~ /^\s*Device\b/i; next unless $ln =~ /\S/; my @p=split(/\s+/,$ln); next unless @p>=4; push @r,{device=>$p[0],total=>$p[1],used=>$p[2],avail=>$p[3]}; } return \@r; }
sub swap_is_active { my ($d)=@_; my $l=swapctl_list(); for my $s(@$l){ return 1 if $s->{device} eq $d || $s->{device} eq "/dev/$d"; } return 0; }
sub swap_on { my ($rc,$out,$err)=run_cmd($SWAPON,$_[0]); return ($rc==0,$err||$out); }
sub swap_off { my ($rc,$out,$err)=run_cmd($SWAPOFF,$_[0]); return ($rc==0,$err||$out); }
sub service_run { run_cmd($SERVICE,$_[0],$_[1]); }
sub network_interfaces_list { my ($rc,$out,$err)=run_cmd($IFCONFIG,'-l'); return [] if $rc!=0||!$out; my @ifs=grep{/^[A-Za-z0-9_.:\-]+$/}split(/\s+/,$out); return \@ifs; }
sub network_interface_details { my ($rc,$out,$err)=run_cmd($IFCONFIG,$_[0]); return $rc==0?($out||''):($err||''); }
sub network_listening_ports {
  my ($rc,$out,$err)=run_cmd($SOCKSTAT,'-l');
  return [] if $rc!=0||!$out;
  my @r;
  for my $ln(split/\n/,$out){
    next if $ln =~ /^USER\s+/;
    next unless $ln =~ /\S/;
    my @p=split(/\s+/,$ln);
    next unless @p>=6;
    my $proto_raw = $p[4] || '';
    my $local = $p[5] || '';
    my $transport = '-';
    my $ipver = '';
    if ($proto_raw =~ /^(tcp|udp)(\d+)?$/i) {
      $transport = uc($1);
      $ipver = $2 || '';
    }
    my $port = '-';
    if ($local =~ /:(\d+)\*?$/) {
      $port = $1;
    } elsif ($local =~ /\.(\d+)$/) {
      $port = $1;
    }
    push @r,{
      user      => $p[0],
      command   => $p[1],
      pid       => $p[2],
      proto     => $proto_raw,
      protocol  => $transport,
      ipver     => $ipver,
      local     => $local,
      port      => $port,
    };
  }
  return \@r;
}
sub firewall_pf_info { my ($rc,$out,$err)=run_cmd($PFCTL,'-s','info'); my $enabled=0; my $status='Unknown'; if($rc==0&&$out){ for my $ln(split/\n/,$out){ if($ln =~ /^\s*Status:\s+(.+)$/i){ $status=$1; $enabled=($status =~ /Enabled/i)?1:0; last; } } } my ($rrc,$rout,$rerr)=run_cmd($PFCTL,'-sr'); my @rules=($rrc==0&&$rout)?grep{/\S/}split(/\n/,$rout):(); return {enabled=>$enabled,status_line=>$status,rules=>\@rules,rules_count=>scalar(@rules)}; }
sub firewall_pf_test { my ($rc,$out,$err)=run_cmd($PFCTL,'-nf',$_[0]); return ($rc==0,$out,$err); }
sub firewall_pf_reload { my ($rc,$out,$err)=run_cmd($PFCTL,'-f',$_[0]); return ($rc==0,$out,$err); }
sub system_reboot_now { must_run($SHUTDOWN,'-r','now'); 1; }
sub system_poweroff_now { must_run($SHUTDOWN,'-p','now'); 1; }
sub mount_legacy { my ($rc,$out,$err)=run_cmd($MOUNT,@_); return ($rc==0,$err||$out); }
sub umount_point { my ($rc,$out,$err)=run_cmd($UMOUNT,$_[0]); return ($rc==0,$err||$out); }
sub md_attach { my (%o)=@_; my @c=($MD,'-a'); push @c,'-t',$o{type} if $o{type}; push @c,'-f',$o{file} if $o{file}; push @c,'-s',$o{size} if $o{size}; my ($rc,$out,$err)=run_cmd(@c); return ($rc==0,$out||$err); }
sub md_detach { my ($rc,$out,$err)=run_cmd($MD,'-d','-u',$_[0]); return ($rc==0,$out||$err); }
sub mdconfig_list { my ($rc,$out,$err)=run_cmd($MD,'-l'); return [] if $rc!=0||!$out; my @u=grep{/\S/}split(/\s+/,$out); return \@u; }
sub extract_tar { my (%o)=@_; my ($rc,$out,$err)=run_cmd($TAR,'-xf',$o{archive},'-C',$o{dest}); die $err if $rc!=0; 1; }

sub parse_ctl_targets {
  my ($raw)=@_; $raw='' unless defined $raw;
  my @t;
  while ($raw =~ /target\s+([^\s{]+)\s*\{(.*?)\n\}\s*/sg) {
    my ($name,$body)=($1,$2); my ($dev,$lun)=('',0);
    if ($body =~ /lun\s+(\d+)\s*\{(.*?)\n\s*\}/sg) { $lun=$1; my $lb=$2; $dev=$1 if $lb =~ /\bpath\s+([^\s\n]+)/; }
    elsif ($body =~ /\bpath\s+([^\s\n]+)/) { $dev=$1; }
    push @t,{name=>$name,device=>$dev,lun=>$lun};
  }
  @t = sort { ($a->{name}||'') cmp ($b->{name}||'') } @t;
  return \@t;
}

# acl helpers --------------------------------------------------------------
sub _acl_path {
  _refresh_ctx();
  return ($module_root_directory || $LIBDIR) . '/acl.txt';
}

sub acl_read {
  my $path = _acl_path();
  my %acl = (
    features => {},
    roles    => {},
    users    => {},
  );

  my $raw = read_file_text($path);
  return \%acl unless defined $raw && length $raw;

  for my $ln (split /\n/, $raw) {
    $ln =~ s/\r$//;
    next if $ln =~ /^\s*#/;
    next if $ln !~ /=/;
    my ($k,$v) = split(/\s*=\s*/, $ln, 2);
    $k = '' unless defined $k;
    $v = '' unless defined $v;
    $k =~ s/^\s+|\s+$//g;
    $v =~ s/^\s+|\s+$//g;
    next unless length $k;

    if ($k =~ /^feature_(.+)$/) {
      $acl{features}{$1} = $v;
    }
    elsif ($k =~ /^role_(.+)$/) {
      my @f = grep { length($_) } map { s/^\s+|\s+$//gr } split(/\s*,\s*/, $v);
      $acl{roles}{$1} = \@f;
    }
    elsif ($k =~ /^user_(.+)$/) {
      my @f = grep { length($_) } map { s/^\s+|\s+$//gr } split(/\s*,\s*/, $v);
      $acl{users}{$1} = \@f;
    }
    else {
      $acl{$k} = $v;
    }
  }
  return \%acl;
}

sub _acl_current_user {
  no warnings 'once';
  return $main::remote_user if defined $main::remote_user && $main::remote_user ne '';
  return $ENV{REMOTE_USER} if defined $ENV{REMOTE_USER} && $ENV{REMOTE_USER} ne '';
  return 'root';
}

sub acl_feature_catalog {
  my $acl = acl_read();
  return $acl->{features} || {};
}

sub acl_get_user_features {
  my ($user) = @_;
  $user = _acl_current_user() unless defined $user && length $user;

  my $acl = acl_read();
  my @features;
  if (exists $acl->{users}{$user}) {
    @features = @{ $acl->{users}{$user} || [] };
  }
  elsif (exists $acl->{roles}{admin}) {
    @features = @{ $acl->{roles}{admin} || [] };
  }
  return \@features;
}

sub acl_write_user_features {
  my ($user, $features) = @_;
  die 'Invalid user' unless defined $user && $user =~ /^[A-Za-z0-9_.-]+$/;
  $features ||= [];
  my @f = grep { defined($_) && $_ =~ /^[A-Za-z0-9_.:-]+$/ } @$features;

  my $path = _acl_path();
  my $raw = read_file_text($path);
  my @lines = length($raw) ? split(/\n/, $raw) : ();
  my $key = "user_$user";
  my $new = $key . '=' . join(',', @f);
  my $found = 0;
  for my $i (0..$#lines) {
    if ($lines[$i] =~ /^\s*\Q$key\E\s*=/) {
      $lines[$i] = $new;
      $found = 1;
      last;
    }
  }
  push @lines, $new unless $found;
  my $out = join("\n", @lines) . "\n";
  write_file_with_backup($path, $out);
  return 1;
}

sub acl_feature_allowed {
  my ($feature, $user) = @_;
  return 1 if !defined $feature || $feature eq '';
  my $allowed = acl_get_user_features($user);
  my %set = map { $_ => 1 } @$allowed;
  return $set{$feature} ? 1 : 0;
}

sub acl_require_feature {
  my ($feature, $user) = @_;
  return 1 if acl_feature_allowed($feature, $user);
  my $who = defined $user && $user ne '' ? $user : _acl_current_user();
  die "Access denied for feature '$feature' (user: $who)";
}

sub acl_level_to_features {
  my ($level) = @_;
  $level = '' unless defined $level;
  my $acl = acl_read();
  my $roles = $acl->{roles} || {};

  if ($level =~ /^(?:admin|administrator)$/i) {
    return [ @{ $roles->{admin} || [] } ];
  }
  if ($level =~ /^(?:operator|manage|manager)$/i) {
    return [ @{ $roles->{operator} || $roles->{admin} || [] } ];
  }
  if ($level =~ /^(?:viewer|view|readonly|read-only)$/i) {
    return [ @{ $roles->{viewer} || [] } ];
  }
  return [];
}

sub acl_features_to_level {
  my ($features) = @_;
  $features ||= [];
  my @f = ref($features) eq 'ARRAY' ? @$features : ();
  my %set = map { $_ => 1 } @f;
  return 'admin'    if $set{acl} || $set{system};
  return 'operator' if $set{pools} || $set{datasets} || $set{disks} || $set{services};
  return 'viewer';
}

1;
