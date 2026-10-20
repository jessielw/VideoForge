# Queue and batch indexing

The queue stores jobs and their settings in SQLite. One worker processes jobs in order; each job
can run audio encodes alongside its video encode. A separate indexing lane prepares sources for
preview and later encoding.

## Add and edit a batch

1. On **New jobs**, add a folder of episodes or select individual sources.
2. Choose a template and add the jobs to the queue.
3. Open a job to check video processing, encoder settings, tracks, and output.
4. Select several jobs to apply an edit or template to all of them.
5. Use **Run selected** for a subset or **Start queue** for the queued jobs.

Each job gets its own settings. Changing one job does not silently change the others.
For episodes with different track orders, prefer template rules over track positions.

## Batch indexing

Use **Index** on the Queue toolbar to index selected jobs, or all jobs if none are selected.
Indexing creates the source index and working script without starting an encode. A job's preview
opens only after its source is indexed; opening an editor never starts a full-source read by itself.

Indexing can run while another job encodes. By default, a source on the same physical disk that
the encode is reading waits, and sources on other disks go first. **Settings** controls this disk wait.

BestSource's first index decodes the whole video and can take substantially longer than FFMS2.
Check the job log before assuming an index is stuck.

## Pause, stop, and cancel

Pause and resume control the running tools. The Queue toolbar also changes the running job's
process priority. Default priorities for later runs are on **Settings**.

Stopping the queue after the current job leaves the remaining jobs queued. Cancelling interrupts
the running work. When VideoForge shuts down, its child tools stop too; a partially encoded stream
is not a finished reusable step.

## Reuse completed work

Before rerunning a job, **Start queue** and **Run selected** show the available completed video and
audio encodes. Choose which to reuse and which to create again. Reuse depends on the saved step
fingerprint and the finished output files; changed inputs or settings can invalidate it.

Intermediate files and `finished-steps.json` live in the source's work folder. Keep that folder to
retain reuse. A process interrupted halfway through an encode restarts that encode rather than
continuing inside its bitstream.

## Read the result

| Status | Meaning | Next step |
| --- | --- | --- |
| Done | Output was muxed and passed its output checks | Inspect playback |
| Invalid | Output exists but failed an output check | Read the output issues |
| Failed | A tool or pipeline step failed | Read the last failed step in Log |
| Skipped | The job could not run, for example because its plan was blocked | Resolve the planning issues |
| Cancelled | The run was interrupted | Rerun and review reuse choices |

Use the job's **Log** tab for one job, or the **Log** page for all jobs. For persistent paths and
cleanup, see [Storage and backups](../configuration/storage.md).
