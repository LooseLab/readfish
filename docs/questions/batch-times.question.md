---
title: "What should my batch times look like."
alt_titles:
  - "batchy batchy bois"
---

When running readfish, you will see output scrolling down your terminal pane to the effect of

```console
2023-10-05 15:25:48,724 readfish.targets 0494R/0.5713s; Avg: 0494R/0.5713s; Seq:0; Unb:494; Pro:0; Slow batches (>1.00s): 0/1
2023-10-05 15:25:52,132 readfish.targets 0004R/0.1831s; Avg: 0249R/0.3772s; Seq:0; Unb:498; Pro:0; Slow batches (>1.00s): 0/2
2023-10-05 15:25:52,600 readfish.targets 0122R/0.2494s; Avg: 0206R/0.3346s; Seq:0; Unb:620; Pro:0; Slow batches (>1.00s): 0/3
2023-10-05 15:25:52,967 readfish.targets 0072R/0.2144s; Avg: 0173R/0.3046s; Seq:0; Unb:692; Pro:0; Slow batches (>1.00s): 0/4
2023-10-05 15:25:53,349 readfish.targets 0043R/0.1932s; Avg: 0147R/0.2823s; Seq:0; Unb:735; Pro:0; Slow batches (>1.00s): 0/5
2023-10-05 15:25:53,759 readfish.targets 0048R/0.2011s; Avg: 0130R/0.2688s; Seq:0; Unb:783; Pro:0; Slow batches (>1.00s): 0/6
2023-10-05 15:25:54,206 readfish.targets 0126R/0.2458s; Avg: 0129R/0.2655s; Seq:0; Unb:909; Pro:0; Slow batches (>1.00s): 0/7
2023-10-05 15:25:54,580 readfish.targets 0082R/0.2180s; Avg: 0123R/0.2595s; Seq:0; Unb:991; Pro:0; Slow batches (>1.00s): 0/8
```

What this means varies a little bit on things like what length of time your signal chunks being read by MinKNOW are, and how good the occupancy on your flow cell is.
Ideally, the time on the right here wants to be less than the amount of time your signal chunks represent.
The default chunk size is 1.0 second, but if you have reduced it just make sure the readfish batch times are roughly in line.
See [this issue repsonse](https://github.com/LooseLab/readfish/issues/221#issuecomment-1547349894) for more information.

This log is a little dense at first. Moving from left to right, we have:

    [Date Time] [Logger Name] [Batch Stats]; [Average Batch Stats]; [Count commands sent]; [Slow Batch Info]

Using the provided log as an example:

On 2023-10-05 at 15:25:56,989, the Readfish targets command logged a batch of read signal:

    - It saw 60 reads in the current batch.
    - The batch took 0.2123 seconds.
    - On average, batches are 103 reads, which are processed in 0.2418 seconds.
    - Since the start, 0 reads were sequenced, 1,442 reads were unblocked, and 0 reads were asked to proceed.
    - Out of 14 total batches processed, 0 were considered slow (took more than 1 second).

In this case, the slow batch field is the information you want to look at. The time represented is automatically grabbed from MinKNOW, using the `break_read_chunks_in_seconds` value.
