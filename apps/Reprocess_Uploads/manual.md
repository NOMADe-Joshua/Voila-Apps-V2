# Reprocess Uploads: User Manual

Admin tool. The experiment parser never overwrites a process entry it already created, so a
parser fix only reaches existing uploads once those entries are gone. This app deletes them and
reprocesses the upload; the parser then writes them again from the experiment Excel, under the
same file name and entry id.

## 1. Search
- **Search in**: "All unpublished uploads" needs the NOMAD admin account; "My uploads" works for
  everyone.
- **Process types**: which entries to recreate. Evaporation is preselected.
- **Evaporation: only entries without stored sources** (on by default) lists only the
  evaporation steps that were stored without their sources.
- Press **Search**. The result lists the files per upload; the line above it says how many
  entries were left out (entries made by hand in the ELN, evaporations that have sources).

## 2. Choose uploads
Tick the uploads to repair (all are ticked after a search); open "upload id" to see every file
that would be deleted.

## 3. Repair
- **Wait per step**: how long to wait for NOMAD to finish a step before giving up on an upload.
- **Repair selected ...** asks for confirmation; only then are files deleted.
- Per upload the app deletes the files, waits until NOMAD is done, reprocesses the upload once
  and checks the result. The log shows each step; **Stop after this upload** ends the run after
  the current upload.
- The result table lists, per upload, the files that were not written again and the evaporation
  entries that still have no sources (then the parser on this Oasis is not the fixed one).

## What it never does
- It never touches entries made by hand in the ELN: only entries the experiment entry lists as
  created by the parser are deleted.
- It never touches published uploads (NOMAD does not allow deleting their files).

## Before you start
- The fixed parser must already run on this Oasis.
- Changes made by hand in the ELN to a recreated entry are lost.
- Try one upload first and check it, for example in Process & JV Overview.
