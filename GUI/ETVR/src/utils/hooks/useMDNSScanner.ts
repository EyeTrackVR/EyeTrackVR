import { invoke } from '@tauri-apps/api/tauri'
import { /* useEffect,  */useState } from 'react'

export const useMDNSScanner = (serviceType: string, scanTime: number) => {
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  /*  useEffect(() => {
     setLoading(true)
     invoke('run_mdns_query', {
       serviceType,
       scanTime
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
   }, [serviceType, scanTime]) */

  const scan = () => {
    setLoading(true)
    invoke('run_mdns_query', {
      serviceType,
      scanTime
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
  }

  return { res, loading, error, scan }
}
