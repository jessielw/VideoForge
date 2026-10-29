import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildTree, groupByFolder, joinName, splitName, type TreeNode } from '../src/lib/templateFolders.ts'

test('a flat list groups by folder path, loose templates first', () => {
  const groups = groupByFolder(['b / X', 'Manual defaults', 'a / c / Y', 'b / Z', 'Loose'], (n) => n)
  assert.deepEqual(
    groups.map((g) => [g.folder, g.items.map((i) => i.label)]),
    [
      ['', ['Manual defaults', 'Loose']],
      ['a / c', ['Y']],
      ['b', ['X', 'Z']],
    ],
  )
})

test('a template name splits into its folders and label, and joins back tidy', () => {
  assert.deepEqual(splitName('Group / 1080p / Film'), { folder: ['Group', '1080p'], label: 'Film' })
  assert.deepEqual(splitName('Film'), { folder: [], label: 'Film' })
  assert.deepEqual(splitName('Show | 1080p'), { folder: [], label: 'Show | 1080p' })
  assert.equal(joinName('Group/1080p', 'Film'), 'Group / 1080p / Film')
  assert.equal(joinName(' a //  b ', ' Film '), 'a / b / Film')
  assert.equal(joinName('', 'Film'), 'Film')
})

test("the tree puts folders first by name, keeps each folder's templates in order and counts them", () => {
  const names = [
    'Loose',
    'Group / 2160p / Film',
    'Group / 1080p / Grain',
    'Anime / TV',
    'Group / 1080p / Film',
    'group / Extra',
  ]
  const tree = buildTree(names, (n) => n)
  const show = (nodes: TreeNode<string>[]): unknown[] =>
    nodes.map((n) => (n.kind === 'folder' ? { [`${n.path} (${n.count})`]: show(n.children) } : n.label))
  assert.deepEqual(show(tree), [
    { 'Anime (1)': ['TV'] },
    { 'Group (4)': [{ 'Group / 1080p (2)': ['Grain', 'Film'] }, { 'Group / 2160p (1)': ['Film'] }, 'Extra'] },
    'Loose',
  ])
})
