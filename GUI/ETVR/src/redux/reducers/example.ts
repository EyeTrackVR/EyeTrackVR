/* eslint-disable */
import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface IInitialState {
  example: boolean
  sagaExample: boolean
}

// here ryou're adding a simple data that you wnat to store
// soon if we want to store data from reducers etc we can use persistate for that

export const initialState: IInitialState = {
  example: false,
  sagaExample: false,
}

const uiSliceManager = createSlice({
  name: 'ui',
  initialState,

  reducers: {
    // loadState(state) {  commented for now becouse we do not have persistate
    //   return state
    // },

    setExample(state, action: PayloadAction<boolean>) {
      // if you want to add more that than that
      // simply change  action: PayloadAction<boolean> to  action: PayloadAction<{a,b}:IProps>
      // and then for example action.payload.a
      state.example = action.payload
    },

    requestSagaExample(state, _: PayloadAction<{ status: boolean }>) {
      // if your're using saga , what you need to do to return only state
    },
    setSagaExample(state, action: PayloadAction<boolean>) {
      state.sagaExample = action.payload
    },
  },
})

export const actions = uiSliceManager.actions
export const reducer = uiSliceManager.reducer
