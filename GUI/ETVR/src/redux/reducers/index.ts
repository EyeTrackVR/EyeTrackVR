import { combineReducers } from '@reduxjs/toolkit'
import { reducer as uiSliceManager } from './example'

// here simply add new reducers
// name:reducer
const combinedReducers = combineReducers({
  ui: uiSliceManager,
})

export default combinedReducers
