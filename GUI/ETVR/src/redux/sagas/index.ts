import { all, spawn } from 'redux-saga/effects'
import { loadUser } from './exampleSaga'

export function* index(): Generator {
  yield all([loadUser].map(spawn))
}

export default index
