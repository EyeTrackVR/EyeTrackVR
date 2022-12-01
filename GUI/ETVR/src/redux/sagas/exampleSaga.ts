/* eslint-disable */
import { actions } from '@redux/reducers/example'
import { all, spawn, takeEvery, put, call } from 'typed-redux-saga'
import { PayloadAction } from '@reduxjs/toolkit'

export function* callExample(status: boolean): Generator {
  //allows to sed data to store
  yield* put(actions.setSagaExample(status))
}

export function* reguestLoadUserHandler(action: PayloadAction<{ status: boolean }>): Generator {
  const status = action.payload.status
  //to call a method you can use yield* call
  yield* call(callExample, status)
}

//simple generator
export function* reguestLoadUserSaga(): Generator {
  // pro tip do not over use yield takevery , it takes every possible request xD
  yield takeEvery(actions.requestSagaExample, reguestLoadUserHandler)
}

export function* loadUser(): Generator {
  yield all([reguestLoadUserSaga].map(spawn))
}
