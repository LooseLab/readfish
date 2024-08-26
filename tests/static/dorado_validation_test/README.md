# Guppy plugin validation test static files

---

This directory holds static files for the guppy plugin validation tests.
These are split into `pass` and `fail` folders, which indicate the expected return code (`0` for pass, `>0` for fail) for the validation of these TOML files.
Files in the `fail` folder are *invalid*.
Files in the `pass` folder will pass validation but may not be useful!

NOTE! The 5555_pass and 5555_fail files in the `pass` and `fail` folder represent Guppy sockets in these tests, however they are not socket files but standard files.

TOML files are paired with TXT files where they share a prefix, e.g:
  - `003_plugin_fail.toml`
  - `003_plugin_fail_0.txt`
  - `003_plugin_fail_1.txt`

These three files share the `003_plugin_fail` prefix.
In the test case the TOML will be validated and then the message in each TXT file will be searched for in the output.
