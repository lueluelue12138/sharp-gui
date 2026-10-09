#!/usr/bin/env python3
"""下载并校验固定 Brush v0.3.0，不改动 Python/CUDA 或全局 PATH。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.brush_engine import BRUSH_COMMIT, BRUSH_INSTALL_RELATIVE_PATH, BRUSH_VERSION


RELEASES = {
    ('windows', 'x86_64'): {
        'archive': 'brush-app-x86_64-pc-windows-msvc.zip',
        'archive_sha256': 'b68e3e9cf052d51bf3ee30776fa5a364de7f2ba13b58443128ff797bb7bcfcd6',
        'binary': 'brush_app.exe',
        'binary_sha256': '37e46cbf808b9983dd15a5f9a25328dbe43e7e06d53c4f59fbeaeb10e3a5b34a',
    },
    ('linux', 'x86_64'): {
        'archive': 'brush-app-x86_64-unknown-linux-gnu.tar.xz',
        'archive_sha256': '4f0f9a8785d1951c62df26aae247c02c5bba32b00f40b06df4e1c9b867399e20',
        'binary': 'brush_app',
        'binary_sha256': '13d28ee06a388bc4e987774e890b594d60a75bba26064e82b4ee338a78f158a4',
    },
    ('darwin', 'arm64'): {
        'archive': 'brush-app-aarch64-apple-darwin.tar.xz',
        'archive_sha256': '65b2631398c839be3c1d4d7160fe2326389dec87830aac0710985e6690a1048c',
        'binary': 'brush_app',
        'binary_sha256': None,
    },
}
REQUIRED_CLI_FLAGS = (
    '--total-steps', '--max-resolution', '--refine-every', '--max-splats',
    '--growth-grad-threshold', '--growth-select-fraction', '--growth-stop-iter',
    '--sh-degree', '--export-path', '--export-name', '--export-every',
)
BRUSH_LICENSE_TEXT = """
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""


def sha256_file(path):
    """流式计算下载包及引擎的 SHA-256。"""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def resolve_release(system=None, machine=None):
    """只有有固定官方包与哈希的平台可以自动安装。"""
    system_name = (system or platform.system()).lower()
    architecture = (machine or platform.machine()).lower()
    architecture = {'amd64': 'x86_64', 'x64': 'x86_64', 'aarch64': 'arm64'}.get(
        architecture, architecture,
    )
    release = RELEASES.get((system_name, architecture))
    if release is None:
        raise RuntimeError(
            'Automatic Brush installation supports Windows x64, Linux x64 and macOS arm64 only. '
            'Build official tag v0.3.0 and set SHARP_BRUSH_EXECUTABLE on other platforms.'
        )
    return {
        **release, 'platform': system_name, 'architecture': architecture,
        'url': f'https://github.com/ArthurBrussee/brush/releases/download/v{BRUSH_VERSION}/{release["archive"]}',
    }


def download_verified_archive(url, destination, expected_sha256):
    """仅在下载完整且哈希匹配后发布缓存；失败不会污染原缓存。"""
    destination = Path(destination)
    if destination.is_file() and sha256_file(destination) == expected_sha256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': f'Sharp-GUI-Brush-Installer/{BRUSH_VERSION}'})
    with tempfile.NamedTemporaryFile(prefix='.brush-download-', dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        if sha256_file(temporary) != expected_sha256:
            raise RuntimeError('Brush archive SHA-256 mismatch; refusing to install changed upstream content')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _safe_archive_target(root, name):
    relative = PurePosixPath(name.replace('\\', '/'))
    if relative.is_absolute() or any(part == '..' or ':' in part for part in relative.parts):
        raise RuntimeError('Unsafe path in Brush archive')
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise RuntimeError('Brush archive path escapes the installation directory')
    return target


def extract_archive(archive, destination):
    """提取经验证的发布包，拒绝路径穿越及链接，不执行包内脚本。"""
    archive, destination = Path(archive), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = _safe_archive_target(destination, member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise RuntimeError('Links are not allowed in the Brush archive')
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
        return
    with tarfile.open(archive, mode='r:xz') as bundle:
        for member in bundle:
            target = _safe_archive_target(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
            else:
                raise RuntimeError('Links and special files are not allowed in the Brush archive')


def verify_brush_cli(executable):
    """只执行版本与 help，确认二进制契约；不会启动训练或图形窗口。"""
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    version = subprocess.run(
        [str(executable), '--version'], check=True, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=20, **options,
    )
    version_text = (version.stdout + version.stderr).strip()
    if version_text.split()[-1:] != [BRUSH_VERSION]:
        raise RuntimeError(f'Unexpected Brush version: {version_text}')
    help_result = subprocess.run(
        [str(executable), '--help'], check=True, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=20, **options,
    )
    help_text = help_result.stdout + help_result.stderr
    missing = [flag for flag in REQUIRED_CLI_FLAGS if flag not in help_text]
    if missing:
        raise RuntimeError('Brush CLI is missing required options: ' + ', '.join(missing))
    return version_text


def _installed_matches(destination, release):
    binary = destination / release['binary']
    metadata = destination / 'INSTALLATION.json'
    if not all(path.is_file() for path in (
        binary, metadata, destination / 'LICENSE.txt', destination / 'THIRD_PARTY_NOTICES.txt',
    )):
        return False
    try:
        installed = json.loads(metadata.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return False
    expected_binary = release['binary_sha256'] or installed.get('binarySha256')
    return bool(
        installed.get('version') == BRUSH_VERSION
        and installed.get('sourceCommit') == BRUSH_COMMIT
        and installed.get('archiveSha256') == release['archive_sha256']
        and expected_binary
        and sha256_file(binary) == expected_binary
        and (destination / 'LICENSE.txt').read_text(encoding='utf-8') == BRUSH_LICENSE_TEXT
    )


def install_brush(destination=None, archive=None, force=False, verify_cli=True):
    """安装固定引擎及许可资料；替换失败时恢复原引擎目录。"""
    release = resolve_release()
    destination = Path(destination or ROOT / BRUSH_INSTALL_RELATIVE_PATH).resolve()
    if destination == ROOT or destination.parent == destination:
        raise RuntimeError('Brush must be installed in a dedicated dependency directory')
    if _installed_matches(destination, release) and not force:
        if verify_cli:
            verify_brush_cli(destination / release['binary'])
        return destination / release['binary']
    if destination.exists() and not force and any(destination.iterdir()):
        raise RuntimeError('Existing Brush installation differs from the lock; rerun with --force to replace it')
    if archive is not None:
        archive = Path(archive).resolve()
        if sha256_file(archive) != release['archive_sha256']:
            raise RuntimeError('Brush archive SHA-256 mismatch; refusing to install')
    else:
        archive = download_verified_archive(
            release['url'], destination.parent / '.downloads' / release['archive'],
            release['archive_sha256'],
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.brush-install-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        extracted = staging / 'release'
        extract_archive(archive, extracted)
        anchors = list(extracted.rglob(release['binary']))
        if len(anchors) != 1:
            raise RuntimeError('Expected exactly one Brush executable in the verified release archive')
        binary_hash = sha256_file(anchors[0])
        if release['binary_sha256'] and binary_hash != release['binary_sha256']:
            raise RuntimeError('Brush executable SHA-256 mismatch; refusing to install')
        installation = staging / 'installation'
        # 保留官方压缩包提供的全部许可证/附带文件，而非只搬运 exe。
        shutil.copytree(extracted, installation / 'upstream-release')
        shutil.copy2(anchors[0], installation / release['binary'])
        (installation / 'LICENSE.txt').write_text(BRUSH_LICENSE_TEXT, encoding='utf-8', newline='\n')
        (installation / 'THIRD_PARTY_NOTICES.txt').write_text(
            f'Brush {BRUSH_VERSION}\nLicense: Apache-2.0\n'
            'Copyright and attribution: Arthur Brussee and Brush contributors.\n'
            f'Upstream source: https://github.com/ArthurBrussee/brush/tree/{BRUSH_COMMIT}\n'
            f'Official release: {release["url"]}\n'
            'The bundled executable is unmodified. LICENSE.txt contains the complete license.\n'
            'Additional files and notices from the official archive are retained under upstream-release/.\n',
            encoding='utf-8',
        )
        metadata = {
            'version': BRUSH_VERSION, 'sourceCommit': BRUSH_COMMIT, 'license': 'Apache-2.0',
            'platform': release['platform'], 'architecture': release['architecture'],
            'sourceUrl': release['url'], 'archiveSha256': release['archive_sha256'],
            'binarySha256': binary_hash,
        }
        (installation / 'INSTALLATION.json').write_text(
            json.dumps(metadata, indent=2) + '\n', encoding='utf-8',
        )
        if verify_cli:
            verify_brush_cli(installation / release['binary'])
        backup = destination.with_name(f'{destination.name}.previous-{uuid.uuid4().hex}')
        had_existing = destination.exists()
        if had_existing:
            os.replace(destination, backup)
        try:
            os.replace(installation, destination)
        except BaseException:
            if had_existing:
                os.replace(backup, destination)
            raise
        if had_existing:
            # 只清理本次刚重命名的专用依赖目录，确认解析后的父目录仍在预期根内。
            if backup.resolve().parent != destination.parent:
                raise RuntimeError('Backup directory escaped the intended installation root')
            shutil.rmtree(backup)
    return destination / release['binary']


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install verified official Brush v0.3.0')
    parser.add_argument('--destination', type=Path, help='Dedicated dependency directory')
    parser.add_argument('--archive', type=Path, help='Use an already downloaded official archive after SHA-256 verification')
    parser.add_argument('--force', action='store_true', help='Replace a different or incomplete installation')
    options = parser.parse_args(argv)
    try:
        executable = install_brush(options.destination, options.archive, options.force)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'[ERROR] Brush installation failed: {error}', file=sys.stderr)
        return 1
    print(f'[OK] Brush {BRUSH_VERSION} installed and CLI verified: {executable}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
