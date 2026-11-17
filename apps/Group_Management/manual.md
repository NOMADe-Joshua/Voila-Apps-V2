# Group Management: User Manual

Admin tool for NOMAD user groups: who is in which group, adding and removing members, creating
and deleting groups. It replaces the group dashboard notebook of the old admin scripts, which
stopped working when the Oasis moved to NOMAD 1.4 and newer.

## Signing in
On the Oasis (opened from the App Dashboard) you are signed in automatically with your NOMAD
account. Outside NOMAD, enter username and password under the connection settings.

The line under the sign-in says whether NOMAD treats the account as its admin. Only the admin
may change every group; everyone else may change only the groups they own or maintain, and
delete only the groups they own. NOMAD checks this itself and refuses anything else.

## Groups
After signing in, every group of the Oasis is listed with its number of members and its owner.
**Filter** narrows the list by name; **Reload groups** reads it again from NOMAD. Selecting a
group shows its id, description and members with their role:

- **owner**: created the group; cannot be removed or changed.
- **maintainer**: may change the group's members.
- **member**: belongs to the group.

## Changing a group
Every change works the same way: fill in the tab, press **Check ...**, read the summary in the
yellow box, then press the **Yes, ...** button. Nothing is written before that second click,
and changing any input or another group cancels the summary.

- **Add members**: email addresses, one per line (commas or spaces also work), and the role
  they get. The summary lists who is added, who is a member already, which addresses have no
  NOMAD account and which text is not an email address.
- **Remove members**: select one or more members of the selected group (Ctrl or Shift for
  several). The owner is not listed.
- **Create group**: name, optional description, optional first members with their role. You
  become the owner. A name that exists already is refused, because two groups of the same name
  are easily mixed up.
- **Delete group**: type the group's name exactly as shown. Uploads shared with the group lose
  that access. A group created again gets a new id, so those uploads would have to be shared
  again.

## What happens when you confirm
1. The group is read again from NOMAD and the change is applied to that current state, so
   members someone else added in the meantime are kept. For a deletion, the app stops if the
   group changed since you checked it.
2. The change (members before and after) is written to the change log. If the log cannot be
   written, nothing is changed in NOMAD.
3. NOMAD is changed.
4. The group is read back and compared with what was written. The message under the box says
   whether NOMAD shows the group as written, or what differs.

## Change log
**Show change log** lists the last changes: time, who, what, which group and the outcome
(`planned`, then `done`, `failed` or `unverified`). Each line of the log file also holds the
complete member lists before and after, so a change can be undone by hand: add or remove the
same people again, or create a deleted group again with its old members.

The log file is `group_changes.log` next to the usage log of the apps, in the folder of the
apps on the Oasis. It holds NOMAD user ids and group names; only admins should open it.

## Known limits
- Roles of existing members cannot be changed here yet; remove the member and add them again
  with the other role.
- The owner of a group cannot be changed (NOMAD does not allow it).
- NOMAD shows no email addresses, so members are listed by name and username.
