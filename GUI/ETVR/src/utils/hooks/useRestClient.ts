import { invoke } from '@tauri-apps/api/tauri'
import { /* useEffect, */ useState } from 'react'

export const useRestClient = (endpoint: string, deviceName: string, method: string) => {
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  /* useEffect(() => {
    setLoading(true)
    invoke('do_rest_request', {
      endpoint,
      deviceName,
      method
    })
      .then((response) => {
        if (typeof response === 'string') {
          const parsedResponse = JSON.parse(response)
          setRes(parsedResponse)
        }
      })
      .catch((err) => {
        setError(err)
      }).finally(() => {
        setLoading(false)
      })
  }, [endpoint, deviceName, method]) */

  const request = () => {
    setLoading(true)
    invoke('do_rest_request', {
      endpoint,
      deviceName,
      method
    })
      .then((response) => {
        if (typeof response === 'string') {
          const parsedResponse = JSON.parse(response)
          console.log(parsedResponse)
          setRes(parsedResponse)
        }
      })
      .catch((err) => {
        console.log(err)
        setError(err)
      }).finally(() => {
        setLoading(false)
      })
  }

  return { res, loading, error, request }
}
