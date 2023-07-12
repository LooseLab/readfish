# Mappy plugin validation test static files

---

This directory holds static files for the mappy plugin validation tests.
These are split into `pass` and `fail` folders, which indicate the expected return code (`0` for pass, `>0` for fail) for the validation of these TOML files.
Files in the `fail` folder are *invalid*.
Files in the `pass` folder will pass validation but may not be useful!

TOML files are paired with TXT files where they share a prefix, e.g:
  - `003_plugin_fail.toml`
  - `003_plugin_fail_0.txt`
  - `003_plugin_fail_1.txt`

These three files share the `003_plugin_fail` prefix.
In the test case the TOML will be validated and then the message in each TXT file will be searched for in the output.
