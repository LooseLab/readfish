---
title: "What should my batch times look like."
alt_titles:
  - "batchy batchy bois"
---

When running readfish, you will see output scrolling down your terminal pane to the effect of

```console
2023-01-17 19:18:57,355 ru.ru_gen 15R/0.50858s
2023-01-17 19:18:57,834 ru.ru_gen 17R/0.47959s
2023-01-17 19:18:58,333 ru.ru_gen 16R/0.49804s
2023-01-17 19:18:58,848 ru.ru_gen 21R/0.51518s
2023-01-17 19:18:59,365 ru.ru_gen 16R/0.51708s
```

What this means varies a little bit on things like what length of time your signal chunks being read by MinKNOW are, and how good the occupancy on your flow cell is.
Ideally, the time on the right here wants to be less than the amount of time your signal chunks represent.
The default chunk size is 1.0 second, but if you have reduced it just make sure the readfish batch times are roughly in line.
See [this issue repsonse](https://github.com/LooseLab/readfish/issues/221#issuecomment-1547349894) for more information.
