/* eslint-disable */
import { useSelector, TypedUseSelectorHook } from 'react-redux'

export interface IExample {
  ui: {
    example: boolean
  }
}

// TODO: we have to create custom keySelector to get all selectors from store

export const customUseSelector: TypedUseSelectorHook<IExample> = useSelector

// for bigger selectors use only createSelector
