import { configureStore, getDefaultMiddleware } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import combinedReducers from './reducers'
import saga from './sagas/index'

const sagaMiddleware = createSagaMiddleware()
const middleware = [
  ...getDefaultMiddleware({ thunk: false, serializableCheck: false }),
  sagaMiddleware,
]

const store = configureStore({
  reducer: combinedReducers,
  middleware,
})

sagaMiddleware.run(saga)

export default store
