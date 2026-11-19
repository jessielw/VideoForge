import assert from 'node:assert/strict'
import { test } from 'node:test'
import { pickAll, pickClick } from '../src/lib/pickPaths.ts'

const order = ['a', 'b', 'c', 'd', 'e']

test('a click toggles one path and keeps the others', () => {
  assert.deepEqual(pickClick([], order, 'c', null, false), ['c'])
  assert.deepEqual(pickClick(['a', 'c'], order, 'c', 'a', false), ['a'])
  assert.deepEqual(pickClick(['e'], order, 'b', 'e', false), ['e', 'b'])
})

test('shift+click ticks the range from the anchor, either way round', () => {
  assert.deepEqual(pickClick(['b'], order, 'd', 'b', true), ['b', 'c', 'd'])
  assert.deepEqual(pickClick(['d'], order, 'a', 'd', true), ['d', 'a', 'b', 'c'])
  // Already-ticked paths keep their place; only new ones are added, in shown order.
  assert.deepEqual(pickClick(['e', 'c'], order, 'b', 'e', true), ['e', 'c', 'b', 'd'])
})

test('shift+click on a ticked path unticks the range', () => {
  assert.deepEqual(pickClick(['a', 'b', 'c', 'd', 'e'], order, 'd', 'b', true), ['a', 'e'])
})

test('shift+click without an anchor in the list is a plain click', () => {
  assert.deepEqual(pickClick([], order, 'c', null, true), ['c'])
  assert.deepEqual(pickClick(['x'], order, 'c', 'x', true), ['x', 'c'])
})

test('pick all ticks every path, or unticks them once all are ticked', () => {
  assert.deepEqual(pickAll(['x', 'b'], ['a', 'b', 'c']), ['x', 'b', 'a', 'c'])
  assert.deepEqual(pickAll(['x', 'a', 'b', 'c'], ['a', 'b', 'c']), ['x'])
  assert.deepEqual(pickAll(['x'], []), ['x'])
})
