# Trigger hunt — host-log forensics in the s2→s3 causal window

Date of hunt: 2026-08-19 ~23:11–23:22 local (15:11–15:22Z), branch
`feature/trigger-hunt`. All host inspection below was **read-only** (no cache
clear/move/touch, no config change); the only host activity in this step is the
session-5 measurement pair in
[`session5-2026-08-19T2321local/`](session5-2026-08-19T2321local/) (established
runner, receipts elsewhere in this directory).

**Causal window.** Session 2's soak receipt ends 2026-08-18T12:01:21Z and
session 3's first receipt starts 2026-08-19T00:56:51Z. Receipts record UTC;
the host clock is **Asia/Shanghai, UTC+8** (`timedatectl`: `Time zone: Asia/
Shanghai (CST, +0800)`, NTP active via systemd-timesyncd). The causal window in
**host local time** is therefore **2026-08-18 20:01:21 → 2026-08-19 08:56:51**.
Every `journalctl --since/--until` and `find -newermt` below uses host-LOCAL
time strings (both parse local by default); bucket boundaries are stated in
local time with the UTC equivalent where useful.

**What this is.** Facts + verbatim command output only. The interpretive layer
(what, if anything, made s3 partial-cold) is H2's; this note draws no causal
conclusions.

## Log-source readability (a finding in itself)

| Source | Readable as user `amd`? | Evidence |
|---|---|---|
| `journalctl` (system + kernel journal) | **YES** | `id`: `groups=...4(adm)...` — boot list and full-window queries return data below |
| `dmesg` | **NO** | `kernel.dmesg_restrict` = `1`; `dmesg -T` → `read kernel buffer failed: Operation not permitted` |
| `/var/log/kern.log` | **YES** (adm, `rw-r----- syslog:adm`) | used as independent corroboration below |
| `/var/log/syslog` | **YES** (adm) | used as independent corroboration below |
| `/var/log/dpkg.log`, `/var/log/apt/{history,term}.log` | **YES** (world-readable) | used below |

Fallback chain: `journalctl` was readable, so `dmesg` was not needed; because
`dmesg` is restricted, `kern.log`/`syslog` serve as the independent second
source (they agree with the journal in every check below).

Host state during the hunt (also the whole window per receipts): up since
**2026-08-12 09:42:38** (`uptime -s`; boot 0 in `journalctl --list-boots`
starts `2026-08-12 09:42:41` and has **no later boot**), power profile
`balanced` (`powerprofilesctl get`), dpm `auto`.

## 1. Suspend/resume hunt — NO events found

Commands and output (verbatim):

```console
$ journalctl --list-boots --no-pager | tail -5
 -1 9d6e108e3b704c1fbc92319ad236c987 Tue 2026-08-11 20:58:47 CST Wed 2026-08-12 09:41:58 CST
  0 5399c684ff8e403d9450b61e234cdaf1 Wed 2026-08-12 09:42:41 CST Wed 2026-08-19 23:13:02 CST

$ journalctl -k --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager \
    | grep -iE "entering sleep|leaving sleep|suspend|resume|PM:"
(0 lines)

$ journalctl --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager \
    | grep -iE "systemd-suspend|sleep\.target|entering sleep|leaving sleep|suspending system|successfully suspended|waking up"
(0 lines)

$ journalctl --since "2026-08-18 00:00:00" --no-pager \
    | grep -iE "entering sleep|leaving sleep|suspending system|successfully suspended|waking up|systemd-suspend"
(0 lines)   # context scan: whole 2026-08-18 00:00 local -> now

$ journalctl -k -b 0 --no-pager | grep -icE "PM: suspend|PM: resume| suspend entry| suspend exit"
0           # whole boot (since 08-12): zero PM suspend/resume lines

$ systemctl status systemd-suspend.service systemd-hibernate.service sleep.target --no-pager | grep Active
     Active: inactive (dead)     (x3)

$ grep -E '^2026-08-18T2[0-3]|^2026-08-19T0[0-8]' /var/log/syslog | grep -iE "suspend|sleep\.target|hibernat"
(0 lines)   # syslog corroboration, same window
```

Kernel-journal coverage inside the window is real, not empty: the window holds
**6** kernel-journal lines (verbatim, all of them — audit/apparmor noise only):

```console
$ journalctl -k --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager
8月 18 23:25:55 amd-HP-ZBook-Ultra systemd-journald[550]: Time jumped backwards, rotating.
8月 19 00:00:01 amd-HP-ZBook-Ultra kernel: kauditd_printk_skb: 9 callbacks suppressed
8月 19 00:00:01 amd-HP-ZBook-Ultra kernel: audit: type=1400 audit(1787068801.721:421): apparmor="DENIED" operation="capable" class="cap" profile="/usr/sbin/cupsd" pid=514236 comm="cupsd" capability=12  capname="net_admin"
8月 19 01:00:10 amd-HP-ZBook-Ultra kernel: audit: type=1400 audit(1787072410.522:422): apparmor="DENIED" operation="capable" class="cap" profile="/usr/sbin/cupsd" pid=540464 comm="cupsd" capability=12  capname="net_admin"
8月 19 06:14:10 amd-HP-ZBook-Ultra kernel: audit: type=1400 audit(1787091250.613:423): apparmor="DENIED" operation="open" class="file" profile="ubuntu_pro_apt_news" name="/opt/rocm-7.2.1/lib/" pid=677183 comm="python3" requested_mask="r" denied_mask="r" fsuid=0 ouid=0
8月 19 06:14:10 amd-HP-ZBook-Ultra kernel: audit: type=1400 audit(1787091250.619:424): apparmor="DENIED" operation="open" class="file" profile="ubuntu_pro_esm_cache" name="/opt/rocm-7.2.1/lib/" pid=677184 comm="python3" requested_mask="r" denied_mask="r" fsuid=0 ouid=0
```

`/var/log/kern.log` independently shows exactly the same 5 kernel lines in the
window (the 6th line above is journald's own, not a kernel message).

## 2. GPU events — NONE in the window or in the whole context scan

```console
$ journalctl -k --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager \
    | grep -iE "amdgpu|gpu reset|ring timeout|page fault|vm fault"
(0 lines)

$ journalctl --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager \
    | grep -iE "amdgpu|gpu reset|ring timeout|page fault|vm fault"
(0 lines)

$ journalctl --since "2026-08-18 00:00:00" --no-pager \
    | grep -iE "amdgpu|gpu reset|ring timeout|page fault|vm fault"
(0 lines)   # context scan 2026-08-18 00:00 local -> now

$ grep -E '^2026-08-18T2[0-3]|^2026-08-19T0[0-8]' /var/log/kern.log | grep -iE "amdgpu|suspend|resume|PM:|gpu|fault"
(0 lines)

$ grep -E '^2026-08-18T2[0-3]|^2026-08-19T0[0-8]' /var/log/syslog | grep -iE "amdgpu|gpu reset|ring timeout|page fault|vm fault"
(0 lines)
```

For scale: the whole boot (08-12 → now) has **136** amdgpu kernel lines, and
the **last** one predates every stability session:

```console
$ journalctl -k -b 0 --no-pager | grep -iE "amdgpu" | tail -5
8月 17 07:27:04 amd-HP-ZBook-Ultra kernel: amdgpu: Freeing queue vital buffer 0x74c45e600000, queue evicted
8月 17 07:27:04 amd-HP-ZBook-Ultra kernel: amdgpu: Freeing queue vital buffer 0x74c4a6200000, queue evicted
8月 17 07:27:04 amd-HP-ZBook-Ultra kernel: amdgpu: Freeing queue vital buffer 0x74d281000000, queue evicted
8月 17 07:27:04 amd-HP-ZBook-Ultra kernel: amdgpu: Freeing queue vital buffer 0x74d2858000000, queue evicted
8月 17 07:27:04 amd-HP-ZBook-Ultra kernel: amdgpu: Freeing queue vital buffer 0x74d286c00000, queue evicted
```

(07:27:04 local on 08-17 = 2026-08-16T23:27Z — during the canonical
2026-08-16T22–23Z hip measurement window; queue-eviction teardown noise, no
reset/fault lines anywhere near the causal window.)

## 3. Power-profile switches — NONE

```console
$ journalctl --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager \
    | grep -iE "power-profiles-daemon|power_profiles|platform_profile|pp_dpm"
(0 lines)

$ journalctl --since "2026-08-18 00:00:00" --no-pager \
    | grep -iE "power-profiles-daemon|power_profiles|platform_profile|pp_dpm"
(0 lines)

$ journalctl -u power-profiles-daemon --since "2026-08-18 20:01:21" --until "2026-08-19 08:56:51" --no-pager | tail -5
-- No entries --    (the daemon logs nothing in this period at all)

$ powerprofilesctl get
balanced

$ ls -la /var/lib/power-profiles-daemon/
(total 8 — directory exists, no state file inside)
```

Caveat recorded: power-profiles-daemon emits no journal lines here even in
normal operation (`-- No entries --` for the whole window), so journal silence
alone would be weak evidence — but the profile is `balanced` now, every
session-4/5 receipt's `telemetry.env` records `power_profile: balanced` at run
time, and no `platform_profile`/`pp_dpm` sysfs-change trace exists in any
source. No switch is visible in any readable log.

## 4. Mesa cache inventory forensics — ZERO writes inside the window

Current state: `~/.cache/mesa_shader_cache` = **7884 KiB / 867 files**
(exactly the session-4 morning reading — no growth today; see the growth note
at the end of this section). No `MESA_SHADER_CACHE_DIR`,
`MESA_SHADER_CACHE_DISABLE`, or `XDG_CACHE_HOME` is set on this host (`env |
grep -iE "MESA|XDG_CACHE|VK_"` → empty).

```console
$ du -sk ~/.cache/mesa_shader_cache ; find ~/.cache/mesa_shader_cache -type f | wc -l
7884 /home/amd/.cache/mesa_shader_cache
867

$ find ~/.cache/mesa_shader_cache -type f \! -newermt "2026-08-18 20:01:21" | wc -l
866      # mtime BEFORE the window

$ find ~/.cache/mesa_shader_cache -type f -newermt "2026-08-18 20:01:21" \
    \! -newermt "2026-08-19 08:56:51" | wc -l
0        # mtime INSIDE the window

$ find ~/.cache/mesa_shader_cache -type f -newermt "2026-08-19 08:56:51" | wc -l
1        # mtime after the window
```

The single post-window file is the cache's empty `marker` file, mtime
2026-08-19 14:32:54 local = 06:32:54Z — the exact start of session-4 run 1
(receipt `started_utc 2026-08-19T06:32:54Z`), i.e. written by session-4, not by
anything in the window. Full mtime history of the 867 files:

```console
$ find ~/.cache/mesa_shader_cache -type f -printf '%TY-%Tm-%Td\n' | sort | uniq -c
    275 2026-05-12
     75 2026-05-13
      6 2026-07-15
     34 2026-08-11
    329 2026-08-12
      1 2026-08-13
      3 2026-08-15
      3 2026-08-16
    140 2026-08-18      # all in the 13:00 hour local — the s1 (v0.1.2) morning session
      1 2026-08-19      # the marker file, 14:32:54 local (session-4 run 1)
```

Newest pre-window files (they match session-4 run 1's receipt
`before_boot.newest_mtime_utc = 2026-08-18T05:47:26Z` = 13:47:26 local):

```console
$ find ~/.cache/mesa_shader_cache -type f -printf '%TY-%Tm-%Td %TH:%TM:%.2TS %p\n' | sort | tail -8
2026-08-18 13:47:25 /home/amd/.cache/mesa_shader_cache/4b/07aae5181346c07279a341828ad802e1bd7df4
2026-08-18 13:47:25 /home/amd/.cache/mesa_shader_cache/e5/81b603ebdd071a74822d8d328ea964f78f6b26
2026-08-18 13:47:25 /home/amd/.cache/mesa_shader_cache/index
2026-08-18 13:47:26 /home/amd/.cache/mesa_shader_cache/7d/2748e7a9cdaf45c0d3e8dc2f4611f103867cea
2026-08-18 13:47:26 /home/amd/.cache/mesa_shader_cache/a9/565080269841d39e6310bd57149beaaadf5be8
2026-08-18 13:47:26 /home/amd/.cache/mesa_shader_cache/b2/8c2deed21a68142c76724eaafb87687de597e2
2026-08-18 13:47:26 /home/amd/.cache/mesa_shader_cache/e7/ac58bdfd35317230658d5561c14f4f1dadbb3a
2026-08-19 14:32:54 /home/amd/.cache/mesa_shader_cache/marker
```

**Survival check:** the pre-window population (866/867 files, 99.9%) still
dominates; nothing was deleted or rewritten inside the window (the receipt
corroboration below also shows the byte size and count were already 7884 KiB /
867 at session-4 time and still are now).

**Receipt cross-check (session-4 run 1, `load.telemetry.mesa_cache`):**
`before_boot` (06:32:54Z 08-19) = 7884 KiB / 867 files, newest mtime
2026-08-18T05:47:26Z — i.e. at the START of session 4, the newest cache write
was still s1's morning write of 08-18. Combined with the buckets above: **no
cache write at all occurred between s1's 08-18 13:47 local write and session-4
run 1's 08-19 14:32 local marker — a span that fully covers s2 (19:28–20:01
local 08-18), the entire causal window, and s3 itself (08:56–08:59 local
08-19).**

Neighbouring RADV state, same result (0 in-window writes):

```console
$ find ~/.cache/radv_builtin_shaders -type f | wc -l
102
$ find ~/.cache/radv_builtin_shaders -type f -newermt "2026-08-18 20:01:21" \
    \! -newermt "2026-08-19 08:56:51" | wc -l
0
# newest files: part9/* 2026-08-18 13:41 (pre-window),
#               marker 2026-08-19 14:32 + part0/mesa_cache.idx 14:41 (session-4 runs 1 and 5)
```

Session-4's aside artifacts (untouched since, kept as evidence):
`~/.cache/mesa_shader_cache.fresh-20260819T064054Z` = 2136 KiB / 100 files,
all mtimes 2026-08-19 14:41 local (session-4 run 5); the `.aside-` dir is gone
(original was moved back and verified 7884 KiB / 867 per the session-4 note).

**atime side-probe** (mount is `ext4 rw,relatime` — `findmnt -T`): 0 files have
atime inside the window; 100 files have atime at 14:32/14:33 local 08-19
(session-4 run 1's reads, >24 h after the last write so relatime allowed the
update). LIMITATION, recorded: under relatime, reads do NOT bump atime when the
previous atime is < 24 h old — s3's own run (08:56 local 08-19) was only ~19 h
after the 08-18 13:47 writes, so **atime evidence cannot confirm or rule out
cache reads by s3**; the mtime evidence above is unaffected by this limitation.

**Cache growth note (pre-session-5 reading, 2026-08-19 23:20:21 local):**
7884 KiB / 867 files — identical to session-4 morning; **zero new compiles
landed in the cache today** before session 5, and session 5's runs left it
unchanged as well (run receipts: before 7884/867 newest 2026-08-19T06:32:54Z →
after 7884/867 newest 2026-08-19T06:32:54Z — the warm-run "no write" pattern
already seen in session-4 run 3).

## 5. Package activity INSIDE the window — one unattended-upgrade transaction

`/var/log/dpkg.log` mtime is 08-19 06:20 local (inside the window). Its
timestamp format is `YYYY-MM-DD HH:MM:SS` (space-separated) — a first grep
keyed on ISO `T` format found nothing and was WRONG; the corrected read:

```console
$ tail /var/log/dpkg.log
2026-08-19 06:20:48 startup archives unpack
2026-08-19 06:20:48 upgrade linux-libc-dev:amd64 6.8.0-137.137 6.8.0-138.138
...
2026-08-19 06:20:48 upgrade linux-tools-common:all 6.8.0-137.137 6.8.0-138.138
...
2026-08-19 06:20:49 status installed man-db:amd64 2.12.0-4build2

$ grep -A4 "^Start-Date: 2026-08-1[89]" /var/log/apt/history.log
Start-Date: 2026-08-19  06:20:48
Commandline: /usr/bin/unattended-upgrade
Upgrade: linux-tools-common:amd64 (6.8.0-137.137, 6.8.0-138.138), linux-libc-dev:amd64 (6.8.0-137.137, 6.8.0-138.138)
End-Date: 2026-08-19  06:20:49
```

Facts: the ONLY package transaction in the window (or on 08-18 at all —
`grep -c "Start-Date: 2026-08-18" /var/log/apt/history.log` = 0) is
unattended-upgrade at **2026-08-19 06:20:48–49 local (2026-08-18T22:20:48Z)**,
upgrading `linux-libc-dev` and `linux-tools-common` 6.8.0-137→6.8.0-138 plus a
man-db trigger. No mesa/vulkan/amdgpu/llvm package appears in dpkg.log since
08-12 (`mesa-vulkan-drivers` is `25.2.8-0ubuntu0.24.04.2` now, matching the
25.2.8 ICD recorded in every session). The journal shows the same transaction:
apt-daily-upgrade.service `Starting`/`Finished` 06:20:45–06:20:50 local.

## 6. Clock events INSIDE the window (recorded verbatim, cause not established)

```console
$ journalctl --since "2026-08-18 23:20:00" --until "2026-08-18 23:30:00" --no-pager | grep -iE "time jump|clock|ntp|chrony|timedate"
8月 18 23:20:10 amd-HP-ZBook-Ultra systemd-resolved[1101]: Clock change detected. Flushing caches.
8月 18 23:21:54 ... (same, repeated)
8月 18 23:23:02 ...
8月 18 23:23:35 ...
8月 18 23:24:10 ...
8月 18 23:24:48 ...
8月 18 23:25:22 ...
8月 18 23:25:55 amd-HP-ZBook-Ultra systemd-resolved[1101]: Clock change detected. Flushing caches.
8月 18 23:25:55 amd-HP-ZBook-Ultra systemd-journald[550]: Time jumped backwards, rotating.
8月 18 23:28:47 ... (one more resolved flush)
```

Eight `Clock change detected` flushes 23:20:10–23:28:47 local 08-18 (inside the
window) and one journald backwards-jump rotation. systemd-timesyncd (the active
NTP service, running since boot) logged **no entries** in the window, so the
stepping source is not identified in any readable log. Receipt UTC stamps on
both sides of the window remain mutually consistent and NTP is currently
synchronized (`timedatectl`: `System clock synchronized: yes`).

## 7. What the window actually contains (characterization)

4250 system-journal lines inside the window, dominated by background noise
(top units by line count: clash-verge-service 3100, systemd 468, cron 296,
systemd-resolved 117, rtkit-daemon 66, dbus-daemon 60, fcitx5 50,
NetworkManager 28, anacron 17, gnome-shell 10). Specifics recorded:

- No user login/session start in the window (`last -F --since 2026-08-18` →
  no entries since 08-18; the only pam session lines are root's cron jobs).
- `ollama` (a GPU-capable service) logged 3 lines, all idle scheduler notices
  ("model recommendations cache sleep scheduled") — no model load.
- `gnome-shell` kept the SAME pid (3326) across the window — no compositor
  restart; only window-manager ping-serial warnings.
- tracker-extract/packagekitd: no entries.

## FACTS summary (no causal claims)

1. No suspend/resume/hibernate event exists in ANY readable source for the
   window, the whole day 08-18, or the whole boot (0 PM lines; single boot
   since 2026-08-12 09:42).
2. No amdgpu kernel line exists anywhere after 2026-08-17 07:27:04 local — the
   causal window and everything since are amdgpu-silent; no GPU reset, ring
   timeout, or page/VM fault in window or context (journal, kern.log, syslog
   agree).
3. No power-profile switch: profile `balanced` at every observation point; no
   platform_profile/pp_dpm/power-profiles-daemon trace in window or context.
4. Mesa cache: 867 files / 7884 KiB, of which 866 pre-window / **0 inside the
   window** / 1 after (session-4's marker at 08-19 14:32:54 local). No
   partial-invalidation rewrite cluster exists; the pre-window population
   survived intact. radv_builtin_shaders likewise: 0 in-window writes.
5. No cache write of any kind occurred between s1's 08-18 13:47 local write
   and session-4 run 1 (08-19 14:32 local) — that span covers s2, the whole
   causal window, and s3's own run.
6. The ONLY host state change found inside the window: unattended-upgrade at
   08-19 06:20:48–49 local upgrading `linux-libc-dev` and
   `linux-tools-common` (6.8.0-137→138); no graphics/GPU packages involved.
7. Eight clock-change detections + one backwards time jump (23:20–23:28 local
   08-18, inside the window); cause not present in readable logs; timesyncd
   silent, currently synchronized.
8. Log readability: journalctl YES (adm), dmesg NO (dmesg_restrict=1),
   kern.log/syslog/dpkg/apt logs YES — all agreeing sources tell the same
   story.
9. Cache size/count today before session 5: 7884 KiB / 867 files — unchanged
   since session-4 morning (no new compiles today); session-5 runs also left
   it unchanged.
