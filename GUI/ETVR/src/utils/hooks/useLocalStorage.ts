import { useEffect, useState } from 'react'

const getStorageData = (keyName: string, defaultValue: unknown) => {
  const savedItem = localStorage.getItem(keyName)
  if (typeof savedItem === 'string') {
    const parsedItem = JSON.parse(savedItem) // ok
    return parsedItem
  }
  return defaultValue
}

export const useLocalStorage = (keyName: string, initialValue: unknown) => {
  const [value, setValue] = useState(() => {
    return getStorageData(keyName, initialValue)
  })

  useEffect(() => {
    localStorage.setItem(keyName, JSON.stringify(value))
  }, [keyName, value])

  return [value, setValue]
}
