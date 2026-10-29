// Template folders: a template's folder is part of its name ("Group / 1080p / Film"), so defaults,
// imports and packs keep naming templates as they always have. The Templates page shows the parts as a tree.
export const SEP = ' / '
const folderParts = (text: string) => text.split('/').map((part) => part.trim())

/** A template name's folders and its own label: "a / b / Film" -> [["a", "b"], "Film"]. */
export function splitName(name: string): { folder: string[]; label: string } {
  const parts = folderParts(name).filter(Boolean)
  return { folder: parts.slice(0, -1), label: parts.at(-1) ?? '' }
}

/** The stored name for a folder ("a/b", as typed) and a label. */
export function joinName(folder: string, label: string): string {
  return [...folderParts(folder), ...folderParts(label)].filter(Boolean).join(SEP)
}

/** One level for a flat list (a select's optgroups): items without a folder first, then each folder path by name. */
export function groupByFolder<T>(
  items: T[],
  nameOf: (item: T) => string,
): { folder: string; items: { item: T; label: string }[] }[] {
  const groups = new Map<string, { item: T; label: string }[]>()
  for (const item of items) {
    const { folder, label } = splitName(nameOf(item))
    const key = folder.join(SEP)
    groups.set(key, [...(groups.get(key) ?? []), { item, label: label || nameOf(item) }])
  }
  return [...groups]
    .map(([folder, items]) => ({ folder, items }))
    .sort((a, b) => (a.folder ? (b.folder ? a.folder.localeCompare(b.folder) : 1) : -1))
}

export type FolderNode<T> = { kind: 'folder'; path: string; name: string; children: TreeNode<T>[]; count: number }
export type TreeNode<T> = FolderNode<T> | { kind: 'item'; item: T; label: string }

/** The templates as a tree: folders first (by name), then the folder's own templates in their order. */
export function buildTree<T>(items: T[], nameOf: (item: T) => string): TreeNode<T>[] {
  const root: FolderNode<T> = { kind: 'folder', path: '', name: '', children: [], count: 0 }
  for (const item of items) {
    const { folder, label } = splitName(nameOf(item))
    let at = root
    for (const part of folder) {
      at.count++
      let next = at.children.find(
        (c): c is FolderNode<T> => c.kind === 'folder' && c.name.toLowerCase() === part.toLowerCase(),
      )
      if (!next) {
        next = { kind: 'folder', path: at.path ? at.path + SEP + part : part, name: part, children: [], count: 0 }
        at.children.push(next)
      }
      at = next
    }
    at.count++
    at.children.push({ kind: 'item', item, label: label || nameOf(item) })
  }
  const order = (nodes: TreeNode<T>[]): TreeNode<T>[] => {
    const folders = nodes
      .filter((n): n is FolderNode<T> => n.kind === 'folder')
      .sort((a, b) => a.name.localeCompare(b.name))
    for (const f of folders) f.children = order(f.children)
    return [...folders, ...nodes.filter((n) => n.kind === 'item')]
  }
  return order(root.children)
}
