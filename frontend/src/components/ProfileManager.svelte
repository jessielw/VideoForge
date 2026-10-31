<script lang="ts">
  import { toast } from 'svelte-sonner'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import * as Dialog from '$lib/components/ui/dialog'
  import { Input } from '$lib/components/ui/input'
  import Tip from './Tip.svelte'
  import { api } from '../lib/api'
  import { app } from '../lib/state.svelte'
  import { saves } from '../lib/saves'
  import { forgetConfigurationDrafts } from '../lib/drafts'
  import type { ConfigState, Profile } from '../lib/types'

  // disabled: Settings has unsaved changes, which belong to the active profile
  let { disabled = false, onswitched }: { disabled?: boolean; onswitched: (config: ConfigState) => void } = $props()

  // One dialog at a time: a new profile, a rename, or a delete
  let dialog = $state<{ kind: 'new' } | { kind: 'rename' | 'delete'; profile: Profile } | null>(null)
  let name = $state('')
  let copy = $state(false)
  let busy = $state(false)
  let error = $state('')
  const switchBlocked = $derived(
    app.queue.running
      ? 'Stop the queue first: its jobs use the active profile’s settings'
      : disabled
        ? 'Wait for Settings to save'
        : '',
  )

  function message(e: unknown): string {
    return e instanceof Error ? e.message : String(e)
  }

  function open(next: NonNullable<typeof dialog>) {
    error = ''
    name = next.kind === 'rename' ? next.profile.name : ''
    copy = false
    dialog = next
  }

  async function submit() {
    if (!dialog) return
    busy = true
    error = ''
    try {
      if (dialog.kind === 'new') app.profiles = await api.createProfile(name, copy)
      else if (dialog.kind === 'rename') app.profiles = await api.renameProfile(dialog.profile.id, name)
      else app.profiles = await api.deleteProfile(dialog.profile.id)
      dialog = null
    } catch (e) {
      error = message(e)
    } finally {
      busy = false
    }
  }

  async function activate(profile: Profile) {
    busy = true
    try {
      await saves.flush()
      const result = await api.activateProfile(profile.id)
      app.profiles = { profiles: result.profiles, active: result.active }
      app.presets = result.presets
      forgetConfigurationDrafts()
      onswitched(result.config)
      toast.success(`Profile: ${profile.name}`, { description: 'Its settings, templates and presets are in use.' })
      await Promise.all([
        api.ruleSets().then((ruleSets) => {
          app.ruleSets = ruleSets
        }),
        app.loadEncoders(),
      ]).catch(() => toast.error('Switched. Reload the page to refresh available rule sets.'))
    } catch (e) {
      toast.error('Profile not switched', { description: message(e) })
    } finally {
      busy = false
    }
  }
</script>

<section class="col-span-full space-y-3" aria-label="Profiles">
  <h2 class="font-medium">Profiles</h2>
  <p class="text-sm text-muted-foreground">
    Each profile holds its own settings, templates and presets; a new one starts as a fresh install does. The queue is
    shared.
  </p>
  <ul class="max-w-xl divide-y rounded-md border">
    {#each app.profiles.profiles as profile (profile.id)}
      {@const active = profile.id === app.profiles.active}
      <li class="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
        <span class="min-w-0 flex-1 truncate" class:font-medium={active}
          >{profile.name}{#if active}<span class="ml-1 text-muted-foreground">(active)</span>{/if}</span
        >
        {#if !active}
          <Tip text={switchBlocked}>
            <Button size="sm" variant="outline" disabled={busy || !!switchBlocked} onclick={() => activate(profile)}
              >Switch</Button
            >
          </Tip>
        {/if}
        <Button size="sm" variant="ghost" disabled={busy} onclick={() => open({ kind: 'rename', profile })}
          >Rename…</Button
        >
        {#if !active}
          <Button size="sm" variant="ghost" disabled={busy} onclick={() => open({ kind: 'delete', profile })}
            >Delete…</Button
          >
        {/if}
      </li>
    {/each}
  </ul>
  <Button variant="outline" disabled={busy} onclick={() => open({ kind: 'new' })}><PlusIcon />New profile…</Button>
</section>

<Dialog.Root
  open={dialog !== null}
  onOpenChange={(value) => {
    if (!value && !busy) dialog = null
  }}
>
  <Dialog.Content class="sm:max-w-md" showCloseButton={!busy}>
    {#if dialog?.kind === 'delete'}
      <Dialog.Header>
        <Dialog.Title>Delete {dialog.profile.name}?</Dialog.Title>
        <Dialog.Description
          >Its settings, templates and presets are removed. Jobs in the queue stay. Export a configuration backup from
          that profile first to keep them.</Dialog.Description
        >
      </Dialog.Header>
    {:else if dialog}
      <Dialog.Header>
        <Dialog.Title>{dialog.kind === 'new' ? 'New profile' : `Rename ${dialog.profile.name}`}</Dialog.Title>
      </Dialog.Header>
      <form
        id="profile-form"
        class="space-y-3 text-sm"
        onsubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <label class="block space-y-1.5">
          <span>Name</span>
          <Input bind:value={name} disabled={busy} maxlength={80} autocomplete="off" />
        </label>
        {#if dialog.kind === 'new'}
          <label class="flex items-start gap-2">
            <Checkbox bind:checked={copy} disabled={busy} />
            <span
              >Copy {app.activeProfile}<span class="block text-xs text-muted-foreground"
                >Start from its settings, templates and presets instead of a fresh install’s.</span
              ></span
            >
          </label>
        {/if}
      </form>
    {/if}
    {#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
    <Dialog.Footer>
      <Button variant="outline" disabled={busy} onclick={() => (dialog = null)}>Cancel</Button>
      {#if dialog?.kind === 'delete'}
        <Button variant="destructive" disabled={busy} onclick={submit}>{busy ? 'Working…' : 'Delete'}</Button>
      {:else}
        <Button type="submit" form="profile-form" disabled={busy || !name.trim()}
          >{busy ? 'Working…' : dialog?.kind === 'new' ? 'Create' : 'Rename'}</Button
        >
      {/if}
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
