<script lang="ts">
  import { onMount } from 'svelte'
  import { ModeWatcher } from 'mode-watcher'
  import LayoutTemplateIcon from '@lucide/svelte/icons/layout-template'
  import ListVideoIcon from '@lucide/svelte/icons/list-video'
  import PanelLeftCloseIcon from '@lucide/svelte/icons/panel-left-close'
  import PanelLeftOpenIcon from '@lucide/svelte/icons/panel-left-open'
  import PlusIcon from '@lucide/svelte/icons/plus'
  import SettingsIcon from '@lucide/svelte/icons/settings'
  import TerminalIcon from '@lucide/svelte/icons/terminal'
  import { Badge } from '$lib/components/ui/badge'
  import { Button } from '$lib/components/ui/button'
  import { Toaster } from '$lib/components/ui/sonner'
  import ThemeToggle from './components/ThemeToggle.svelte'
  import { installDrops } from './lib/dropPaths.svelte'
  import { router, type Page } from './lib/router.svelte'
  import { layout } from './lib/layout.svelte'
  import { app } from './lib/state.svelte'
  import NewJobs from './pages/NewJobs.svelte'
  import Queue from './pages/Queue.svelte'
  import Log from './pages/Log.svelte'
  import Settings from './pages/Settings.svelte'
  import Templates from './pages/Templates.svelte'

  const NAV: { page: Page; label: string; icon: typeof PlusIcon }[] = [
    { page: 'new', label: 'New jobs', icon: PlusIcon },
    { page: 'queue', label: 'Queue', icon: ListVideoIcon },
    { page: 'templates', label: 'Templates', icon: LayoutTemplateIcon },
    { page: 'log', label: 'Log', icon: TerminalIcon },
    { page: 'settings', label: 'Settings', icon: SettingsIcon },
  ]

  onMount(() => {
    installDrops()
    void app.start()
  })

  const running = $derived(app.jobs.find(j => j.status === 'running'))
</script>

<ModeWatcher defaultMode="system" modeStorageKey="videoforge.mode" />
<Toaster richColors closeButton position="bottom-right" />

{#if app.stopped}
  <div class="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-background p-6 text-center" role="alert">
    <img src="/favicon.svg" alt="" class="size-12" />
    <h1 class="text-xl font-semibold">VideoForge has stopped</h1>
    <p class="text-sm text-muted-foreground">
      Start it again with <code>videoforge serve</code>, then reload this page.
    </p>
  </div>
{/if}

<div class="flex h-full">
  <nav class="flex {layout.navCollapsed ? 'w-14' : 'w-48'} shrink-0 flex-col border-r bg-card">
    <div class="flex items-center gap-2 py-4 {layout.navCollapsed ? 'justify-center' : 'px-4'}">
      <img src="/favicon.svg" alt="" class="size-6" title={app.version ? `VideoForge ${app.version}` : undefined} />
      {#if !layout.navCollapsed}
        <span class="text-base font-semibold tracking-wide">VideoForge</span>
        {#if app.version}<span class="text-xs text-muted-foreground tabular-nums">{app.version}</span>{/if}
      {/if}
    </div>
    <div class="flex flex-col gap-0.5 px-2">
      {#each NAV as item (item.page)}
        <Button
          variant="ghost"
          class="relative justify-start gap-3 {layout.navCollapsed ? 'justify-center px-0' : 'px-3'}
            {router.page === item.page ? 'bg-primary/15 text-primary hover:bg-primary/20 hover:text-primary' : 'text-muted-foreground'}"
          aria-current={router.page === item.page ? 'page' : undefined}
          onclick={() => router.go(item.page)}
          title={layout.navCollapsed ? item.label : undefined}
        >
          <item.icon class="size-[18px]" />
          {#if !layout.navCollapsed}{item.label}{/if}
          {#if item.page === 'queue' && app.jobs.length}
            <Badge
              variant="secondary"
              class="tabular-nums {layout.navCollapsed ? 'absolute -top-1 -right-1 h-4 px-1 text-[10px]' : 'ml-auto'}"
              >{app.jobs.length}</Badge
            >
          {/if}
        </Button>
      {/each}
    </div>

    <div class="mt-auto flex flex-col gap-0.5 px-2 pb-1 {layout.navCollapsed ? 'items-center' : ''}">
      <ThemeToggle compact={layout.navCollapsed} />
      <Button
        variant="ghost"
        size={layout.navCollapsed ? 'icon' : 'default'}
        class="text-muted-foreground {layout.navCollapsed ? '' : 'justify-start gap-3 px-3'}"
        onclick={() => (layout.navCollapsed = !layout.navCollapsed)}
        title={layout.navCollapsed ? 'Expand the menu' : 'Collapse the menu'}
      >
        {#if layout.navCollapsed}<PanelLeftOpenIcon />{:else}<PanelLeftCloseIcon />Collapse{/if}
      </Button>
    </div>
    {#if layout.navCollapsed}
      <div class="flex flex-col items-center gap-1 border-t py-3 text-xs">
        {#if running}
          <span class="text-info" title="Running {running.name}{running.progress ? `: ${running.progress.step}` : ''}"
            >{running.progress ? Math.round(running.progress.overall * 100) + '%' : '▶'}</span
          >
        {/if}
        <span class={app.connected ? 'text-success' : 'text-destructive'} title={app.connected ? 'Connected' : 'Reconnecting…'}>●</span>
      </div>
    {:else}
      <div class="space-y-1 border-t p-3 text-xs text-muted-foreground">
        {#if running}
          <div class="truncate text-info" title={running.name}>▶ {running.name}</div>
          {#if running.progress}
            <div class="h-1.5 overflow-hidden rounded bg-muted">
              <div class="h-full bg-info" style="width: {running.progress.overall * 100}%"></div>
            </div>
            <div class="truncate">{running.progress.step}</div>
          {/if}
        {:else}
          <div>{app.queue.queued ? `${app.queue.queued} queued` : 'Idle'}</div>
        {/if}
        {#if app.queue.indexing || app.queue.index_queued}
          {@const left = (app.queue.indexing ? 1 : 0) + app.queue.index_queued}
          <div class="truncate text-info">Indexing {left} job{left > 1 ? 's' : ''}</div>
        {/if}
        <div class={app.connected ? 'text-success' : 'text-destructive'}>{app.connected ? '● connected' : '● reconnecting…'}</div>
      </div>
    {/if}
  </nav>

  <main class="min-w-0 flex-1 overflow-hidden">
    {#if app.connectionError}
      <div class="m-6 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-destructive">
        Couldn't reach the VideoForge server: {app.connectionError}
        <Button class="ml-3" variant="outline" disabled={app.connection === 'retrying'} onclick={() => app.start()}>Retry now</Button>
      </div>
    {/if}
    {#if router.page === 'new'}
      <NewJobs />
    {:else if router.page === 'queue'}
      <Queue />
    {:else if router.page === 'templates'}
      <Templates />
    {:else if router.page === 'settings'}
      <Settings />
    {:else}
      <Log />
    {/if}
  </main>
</div>
