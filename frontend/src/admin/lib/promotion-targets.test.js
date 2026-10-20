import { expect, test } from 'vitest'
import { ALL_PROMOTION_CATEGORIES, SAVED_PROMOTION_SCOPE, initialPromotionTargets, promotionCategoryOptions, promotionTargetBody, promotionTopCategories } from './promotion-targets.js'

test('a parent category covers its sub-categories, where the products actually are', () => {
  const tree = [{ CategoryId: 'phones' }, { CategoryId: 'battery', ParentCategoryId: 'phones' }, { CategoryId: 'iphone', ParentCategoryId: 'phones' }, { CategoryId: 'laptops' }]
  const items = [{ ProductId: 'p1', CategoryId: 'battery' }, { ProductId: 'p2', CategoryId: 'iphone' }, { ProductId: 'p3', CategoryId: 'laptops' }]
  const body = promotionTargetBody(choice('phones'), items, tree)
  expect(body).toEqual({ ProductIds: [], CategoryIds: ['phones', 'battery', 'iphone'] })
  expect(promotionTargetBody(choice('battery'), items, tree)).toEqual({ ProductIds: [], CategoryIds: ['battery'] })
  expect(promotionTargetBody(choice('phones', false, ['p1', 'p2']), items, tree)).toEqual({ ProductIds: ['p1', 'p2'], CategoryIds: [] })
  expect(() => promotionTargetBody(choice('phones', false, ['p3']), items, tree)).toThrow('không thuộc danh mục hiện tại')

  const saved = { Products: [], Categories: body.CategoryIds.map((CategoryId) => ({ CategoryId })) }
  expect(initialPromotionTargets(saved, items, tree)).toMatchObject({ categoryId: 'phones', allProducts: true })
  expect(promotionTopCategories(body.CategoryIds, tree)).toEqual(['phones'])
  expect(initialPromotionTargets({ Products: [{ ProductId: 'p1' }, { ProductId: 'p2' }], Categories: [] }, items, tree)).toMatchObject({ categoryId: 'phones', allProducts: false })
  expect(promotionCategoryOptions(tree).map(({ category, depth }) => `${depth}:${category.CategoryId}`)).toEqual(['0:phones', '1:battery', '1:iphone', '0:laptops'])
})

const products = [{ ProductId: 'p1', CategoryId: 'phones' }, { ProductId: 'p2', Category: { CategoryId: 'phones' } }, { ProductId: 'p3', CategoryId: 'laptops' }]
const categories = [{ CategoryId: 'phones' }, { CategoryId: 'laptops' }, { CategoryId: 'empty' }]
const choice = (categoryId, allProducts = true, productIds = []) => ({ categoryId, allProducts, productIds, changed: true })

test('new promotions require a category first while all categories maps to global scope', () => {
  const initial = initialPromotionTargets(null, products)
  expect(initial.categoryId).toBe('')
  expect(() => promotionTargetBody(initial, products, categories)).toThrow('Vui lòng chọn danh mục')
  expect(promotionTargetBody(choice(ALL_PROMOTION_CATEGORIES), products, categories)).toEqual({ ProductIds: [], CategoryIds: [] })
})

test('all products targets the category, including categories that do not yet have products', () => {
  for (const categoryId of ['phones', 'empty']) expect(promotionTargetBody(choice(categoryId), products, categories)).toEqual({ ProductIds: [], CategoryIds: [categoryId] })
})

test('explicit products never send category targets, even when every current product is selected', () => {
  expect(promotionTargetBody(choice('phones', false, ['p1', 'p2', 'p1']), products, categories)).toEqual({ ProductIds: ['p1', 'p2'], CategoryIds: [] })
})

test('empty subsets and products from another category cannot be submitted', () => {
  expect(() => promotionTargetBody(choice('phones', false), products, categories)).toThrow('Vui lòng chọn ít nhất một sản phẩm')
  expect(() => promotionTargetBody(choice('phones', false, ['p1', 'p3']), products, categories)).toThrow('không thuộc danh mục hiện tại')
  expect(() => promotionTargetBody(choice('removed'), products, categories)).toThrow('Vui lòng chọn danh mục')
})

test('reopening a product subset restores the category and selections without broadening scope', () => {
  const row = { Products: [{ ProductId: 'p1' }, { ProductId: 'p2' }], Categories: [] }
  const selection = initialPromotionTargets(row, products)
  expect(selection).toMatchObject({ categoryId: 'phones', allProducts: false, productIds: ['p1', 'p2'] })
  expect(promotionTargetBody(selection, products, categories, row)).toEqual({ ProductIds: ['p1', 'p2'], CategoryIds: [] })
  expect(initialPromotionTargets({ Products: [], Categories: [{ CategoryId: 'phones' }] }, products)).toMatchObject({ categoryId: 'phones', allProducts: true })
  expect(initialPromotionTargets({ Products: [], Categories: [] }, products).categoryId).toBe(ALL_PROMOTION_CATEGORIES)
})

test('legacy mixed scopes survive unrelated edits until the user explicitly replaces them', () => {
  const row = { Products: [{ ProductId: 'p1' }], Categories: [{ CategoryId: 'laptops' }, { CategoryId: 'empty' }] }
  const selection = initialPromotionTargets(row, products)
  expect(selection.categoryId).toBe(SAVED_PROMOTION_SCOPE)
  expect(promotionTargetBody(selection, products, categories, row)).toEqual({ ProductIds: ['p1'], CategoryIds: ['laptops', 'empty'] })
  expect(promotionTargetBody(choice('phones'), products, categories, row)).toEqual({ ProductIds: [], CategoryIds: ['phones'] })
})
