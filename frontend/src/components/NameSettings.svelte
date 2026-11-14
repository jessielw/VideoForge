<script lang="ts" module>
  import { api } from '../lib/api'
  import type { NameTokens } from '../lib/types'

  // The tokens don't change while the page is open: one request for every editor.
  let tokens: Promise<NameTokens> | null = null
  const loadTokens = () => (tokens ??= api.nameTokens().catch((e) => ((tokens = null), Promise.reject(e))))
</script>

<script lang="ts">
  // The output's naming (core/naming.py), as rows of the Output grid it sits in: the name template (with its
  // tokens), what it names (the file, an MKV's title) and the suffix before the extension. The Output tab and the
  // Templates page both use it; onchange gets the whole MuxSettings.
  import type { MuxSettings, NamePolicy, NameUse } from '../lib/types'
  import BracesIcon from '@lucide/svelte/icons/braces'
  import { Button } from '$lib/components/ui/button'
  import { Checkbox } from '$lib/components/ui/checkbox'
  import { Input } from '$lib/components/ui/input'
  import { Textarea } from '$lib/components/ui/textarea'
  import * as Popover from '$lib/components/ui/popover'
  import Tip from './Tip.svelte'
  import { openSettings } from '../lib/settingsLink'

  let {
    mux,
    mkv,
    disabled = false,
    title = null,
    policy = null,
    ruleSetName = '',
    onchange,
  }: {
    mux: MuxSettings
    mkv: boolean // the container is MKV: the template can name its title
    disabled?: boolean
    title?: string | null // the job's title from the template, to show (none on the Templates page)
    // Settings' word for the rule set's jobs (the Templates page: it wins over these switches when the template
    // is applied); none on a job, whose own switches are what it does
    policy?: NamePolicy | null
    ruleSetName?: string
    onchange: (mux: MuxSettings) => void
  } = $props()

  const given = (use: NameUse | undefined, own: boolean) => (!use || use === 'template' ? own : use === 'on')
  const fileName = $derived(given(policy?.file_name, mux.template_file_name))
  const mkvTitle = $derived(mkv && given(policy?.title, mux.template_title))
  // what Settings decides instead of this template, as words
  const overridden = $derived(
    [
      policy && policy.file_name !== 'template' ? `the file name is always ${policy.file_name}` : '',
      mkv && policy && policy.title !== 'template' ? `the MKV title is always ${policy.title}` : '',
    ].filter(Boolean),
  )

  // Loaded when the field or the token list is first used, not with the page.
  let info = $state<NameTokens | null>(null)
  let open = $state(false)
  function load() {
    if (info) return
    loadTokens().then(
      (t) => (info = t),
      () => {}, // the field still works; the token list just stays empty
    )
  }

  const set = (patch: Partial<MuxSettings>) => onchange({ ...mux, ...patch })
  const used = $derived(fileName || mkvTitle)
  const whose = $derived(ruleSetName ? `all ${ruleSetName} jobs` : "all of this rule set's jobs")

  // Tokens go in at the cursor (the end before the field was used), and come back selected so it shows where.
  let field = $state<HTMLTextAreaElement | null>(null)
  let caret: number | null = null
  const keepCaret = () => (caret = field?.selectionEnd ?? null)
  const oneLine = (text: string) => text.replace(/\s*\n\s*/g, ' ').trim()

  function insert(name: string) {
    const typed = oneLine(field?.value ?? '')
    const text = typed || info?.default_template || ''
    const at = typed ? Math.min(caret ?? text.length, text.length) : text.length // the default: at its end
    const before = text.slice(0, at)
    const after = text.slice(at)
    const token = `{${name}}`
    const lead = before && !/\s$/.test(before) ? ' ' : ''
    const trail = after && !/^\s/.test(after) ? ' ' : ''
    const start = before.length + lead.length
    set({ name_template: before + lead + token + trail + after })
    open = false
    caret = start + token.length
    requestAnimationFrame(() => {
      field?.focus()
      field?.setSelectionRange(start, start + token.length)
    })
  }
</script>

<span class="text-muted-foreground">Name template</span>
<div class="min-w-0 space-y-2">
  <div class="flex items-start gap-2">
    <Textarea
      bind:ref={field}
      class="min-h-14 flex-1 resize-none font-mono text-xs"
      rows={2}
      aria-label="Name template"
      placeholder={info?.default_template ?? 'Empty uses the default template (see Tokens)'}
      value={mux.name_template}
      {disabled}
      spellcheck={false}
      onfocus={load}
      onselect={keepCaret}
      onkeyup={keepCaret}
      onclick={keepCaret}
      onblur={keepCaret}
      onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), field?.blur())}
      onchange={(e) => set({ name_template: oneLine((e.target as HTMLTextAreaElement).value) })}
    />
    <Popover.Root bind:open onOpenChange={(v) => v && load()}>
      <Tip text="The tokens a name template can use">
        <Popover.Trigger {disabled}>
          {#snippet child({ props })}
            <Button {...props} variant="outline"><BracesIcon />Tokens</Button>
          {/snippet}
        </Popover.Trigger>
      </Tip>
      <Popover.Content
        align="end"
        class="max-h-(--bits-floating-available-height) w-[34rem] max-w-[90vw] space-y-2 overflow-auto p-3 text-sm"
      >
        <p class="text-xs text-muted-foreground">
          Click a token to add it at the cursor in the template. An empty token is dropped with the space before it.
          <code>{'{:opt=-:token}'}</code> puts "-" before a value only when there is one. Filters:
          <code>{(info?.filters ?? []).map((f) => `|${f}`).join(' ')}</code>
          (<code>{'{title|dots}'}</code>). Other text stays as typed, so a group tag is just <code>-GRP</code>.
        </p>
        {#if info}
          <p class="text-xs text-muted-foreground">
            Empty uses: <code class="break-all">{info.default_template}</code>
          </p>
        {/if}
        <ul class="divide-y rounded-lg border">
          {#each info?.tokens ?? [] as t (t.name)}
            <li>
              <button
                type="button"
                class="flex w-full items-baseline gap-3 px-2 py-1.5 text-left hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                onclick={() => insert(t.name)}
              >
                <code class="shrink-0 font-mono text-xs">{`{${t.name}}`}</code>
                <span class="text-xs text-muted-foreground">{t.description}</span>
              </button>
            </li>
          {/each}
        </ul>
      </Popover.Content>
    </Popover.Root>
  </div>
  <div class="flex flex-wrap gap-x-5 gap-y-1">
    <label class="flex items-center gap-2">
      <Checkbox
        checked={mux.template_file_name ?? false}
        {disabled}
        onCheckedChange={(v) => set({ template_file_name: v })}
      />
      Name the file with it
    </label>
    {#if mkv}
      <label class="flex items-center gap-2">
        <Checkbox
          checked={mux.template_title ?? false}
          {disabled}
          onCheckedChange={(v) => set({ template_title: v })}
        />
        Set the MKV title with it
      </label>
    {/if}
  </div>
  <p class="text-xs text-muted-foreground">
    {#if overridden.length}
      Settings decides this for {whose}: {overridden.join(' and ')}, whatever this template says.
    {:else}
      Settings can turn these on or off for {whose} at once.
    {/if}
    <button
      type="button"
      class="underline underline-offset-2 hover:text-foreground"
      onclick={() => openSettings('jobs', 'output-names')}>Settings → Output names</button
    >
  </p>
  {#if !used}
    <p class="text-xs text-muted-foreground">Not used until one of these is on. Empty uses the template shown.</p>
  {:else if title}
    <Tip class="block font-mono text-xs break-all text-muted-foreground" text="The MKV title this job writes"
      >Title: {title}</Tip
    >
  {/if}
</div>
<span class="text-muted-foreground">Name suffix</span>
<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
  <Input
    class="w-32 font-mono text-xs"
    aria-label="Name suffix"
    placeholder="e.g. vf"
    value={mux.name_suffix}
    {disabled}
    onchange={(e) => set({ name_suffix: (e.target as HTMLInputElement).value.trim() })}
  />
  <span class="text-xs text-muted-foreground">Goes before the extension: <code>name.vf.mkv</code></span>
</div>
