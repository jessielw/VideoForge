<script lang="ts">
  // The VapourSynth script, StaxRip-style: the generated head and tail (read-only, dimmed) around
  // the editable body, numbered like the script vspipe runs, with the failing line marked.
  // Ctrl+Enter runs; Tab indents; Enter keeps the indentation (one level more after a colon).
  let {
    head,
    tail,
    body = $bindable(''),
    errorLine = null,
    disabled = false,
    onrun,
  }: {
    head: string[]
    tail: string[]
    body?: string
    errorLine?: number | null
    disabled?: boolean
    onrun: () => void
  } = $props()

  const INDENT = '    '
  const bodyLines = $derived(body.split('\n'))
  const total = $derived(head.length + bodyLines.length + tail.length)
  const widest = $derived(Math.max(0, ...[...head, ...bodyLines, ...tail].map(l => l.length)))
  const bodyError = $derived(
    errorLine !== null && errorLine > head.length && errorLine <= head.length + bodyLines.length
      ? errorLine - head.length - 1
      : null,
  )

  // insertText keeps the browser's undo history and fires `input` (which updates `body`).
  function insert(ta: HTMLTextAreaElement, text: string) {
    if (!document.execCommand('insertText', false, text)) {
      ta.setRangeText(text, ta.selectionStart, ta.selectionEnd, 'end')
      body = ta.value
    }
  }

  function onkeydown(e: KeyboardEvent) {
    const ta = e.currentTarget as HTMLTextAreaElement
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      onrun()
    } else if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault()
      insert(ta, INDENT)
    } else if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
      e.preventDefault()
      const line = ta.value.slice(ta.value.lastIndexOf('\n', ta.selectionStart - 1) + 1, ta.selectionStart)
      const indent = /^\s*/.exec(line)![0] + (line.trimEnd().endsWith(':') ? INDENT : '')
      insert(ta, '\n' + indent)
    }
  }
</script>

<div class="min-h-0 flex-1 overflow-auto rounded-md border border-line bg-panel font-mono text-xs leading-5">
  <div class="flex min-h-full min-w-max">
    <div class="sticky left-0 shrink-0 border-r border-line bg-panel px-2 text-right text-muted select-none">
      {#each { length: total } as _, i (i)}
        <div class={i + 1 === errorLine ? 'font-semibold text-bad' : ''}>{i + 1}</div>
      {/each}
    </div>
    <div class="flex-1" style="min-width:calc({widest}ch + 2rem)">
      {#each head as line, i (i)}
        <div class="px-2 whitespace-pre text-muted/70 {i + 1 === errorLine ? 'bg-bad/20' : ''}">{line || ' '}</div>
      {/each}
      <div class="relative">
        {#if bodyError !== null}
          <div class="pointer-events-none absolute inset-x-0 h-5 bg-bad/20" style="top:{bodyError * 1.25}rem"></div>
        {/if}
        <textarea
          class="relative block w-full resize-none overflow-hidden border-0 bg-transparent px-2 py-0 leading-5 whitespace-pre outline-none
            focus:bg-accent/5 disabled:opacity-70"
          rows={bodyLines.length}
          wrap="off"
          spellcheck="false"
          autocomplete="off"
          aria-label="Script body"
          placeholder="# Empty: the source is encoded as it is. Lines here read and reassign `clip`."
          {disabled}
          bind:value={body}
          {onkeydown}
        ></textarea>
      </div>
      {#each tail as line, i (i)}
        {@const n = head.length + bodyLines.length + i + 1}
        <div class="px-2 whitespace-pre text-muted/70 {n === errorLine ? 'bg-bad/20' : ''}">{line || ' '}</div>
      {/each}
    </div>
  </div>
</div>
