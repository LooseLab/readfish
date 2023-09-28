---
title: "KeyError: 'adapter'"
alt_titles:
  - "self.lookup_read_class[x] for x in self.prefilter_classe"
---
If you see something like:

```console
Traceback (most recent call last):
  File "/home/adoni5/mambaforge/envs/readfish_dev/bin/readfish", line 8, in <module>
    sys.exit(main())
  File "/home/adoni5/Projects/readfish_dev/src/readfish/_cli_base.py", line 59, in main
    raise SystemExit(args.func(parser, args, extras))
  File "/home/adoni5/Projects/readfish_dev/src/readfish/entry_points/targets.py", line 412, in run
    read_until_client = RUClient(
  File "/home/adoni5/Projects/readfish_dev/src/readfish/_read_until_client.py", line 40, in __init__
    super().__init__(*args, **kwargs)
  File "/home/adoni5/.local/lib/python3.10/site-packages/read_until/base.py", line 201, in __init__
    self.strand_classes = set(
  File "/home/adoni5/.local/lib/python3.10/site-packages/read_until/base.py", line 202, in <genexpr>
    self.lookup_read_class[x] for x in self.prefilter_classes
KeyError: 'adapter'
```

Try starting readfish about 1 second longer in to the run you eager beaver. `Getting to 35°C` is a good time to start readfish.
