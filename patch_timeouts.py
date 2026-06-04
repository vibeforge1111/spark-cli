#!/usr/bin/env python3
"""One-shot patch to add timeouts to git subprocess calls."""
cli = "src/spark_cli/cli.py"
with open(cli, "rb") as f:
    content = f.read()

CRLF = b"\r\n"
le = CRLF if CRLF in content else b"\n"

patches = []

# 1. run_git_or_exit - add timeout=120 + TimeoutExpired handler
old1 = le.join([
    b'            capture_output=True,',
    b'            text=True,',
    b'        )',
    b'    except OSError as exc:',
])
new1 = le.join([
    b'            capture_output=True,',
    b'            text=True,',
    b'            timeout=120,',
    b'        )',
    b'    except subprocess.TimeoutExpired as exc:',
    b'        raise SystemExit(',
    b'            f"git operation failed for {name}: git command timed out after {exc.timeout}s"',
    b'        ) from exc',
    b'    except OSError as exc:',
])
patches.append((old1, new1, "run_git_or_exit timeout+handler"))

# 2. verify_pinned_commit - add timeout=120
old2 = le.join([
    b'    verify_result = subprocess.run(',
    b'        git_command("-C", str(target), "verify-commit", commit),',
    b'        capture_output=True,',
    b'        text=True,',
    b'    )',
])
new2 = le.join([
    b'    verify_result = subprocess.run(',
    b'        git_command("-C", str(target), "verify-commit", commit),',
    b'        capture_output=True,',
    b'        text=True,',
    b'        timeout=120,',
    b'    )',
])
patches.append((old2, new2, "verify_pinned_commit timeout"))

# 3. clone_module_source bare clone - add timeout=300
old3 = le.join([
    b'    result = subprocess.run(',
    b'        git_command("clone", "--depth=1", url, str(target)),',
    b'        capture_output=True,',
    b'        text=True,',
    b'    )',
    b'    if result.returncode != 0:',
])
new3 = le.join([
    b'    result = subprocess.run(',
    b'        git_command("clone", "--depth=1", url, str(target)),',
    b'        capture_output=True,',
    b'        text=True,',
    b'        timeout=300,',
    b'    )',
    b'    if result.returncode != 0:',
])
patches.append((old3, new3, "clone_module_source timeout"))

# 4. pull_module_source - add timeout=120
old4 = le.join([
    b'    result = subprocess.run(',
    b'        git_command("-C", str(path), "pull", "--ff-only"),',
    b'        capture_output=True,',
    b'        text=True,',
    b'    )',
    b'    return result.returncode == 0, summarize_command_output(result)',
])
new4 = le.join([
    b'    result = subprocess.run(',
    b'        git_command("-C", str(path), "pull", "--ff-only"),',
    b'        capture_output=True,',
    b'        text=True,',
    b'        timeout=120,',
    b'    )',
    b'    return result.returncode == 0, summarize_command_output(result)',
])
patches.append((old4, new4, "pull_module_source timeout"))

applied = 0
for old, new, name in patches:
    if old in content:
        content = content.replace(old, new, 1)
        applied += 1
        print(f"  {name}: OK")
    else:
        print(f"  {name}: NOT FOUND")

with open(cli, "wb") as f:
    f.write(content)
print(f"\n{applied}/{len(patches)} patches applied")
