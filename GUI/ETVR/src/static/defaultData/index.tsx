import { faDroplet } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IdropDataData } from '../interfaces'

export const DropDataData: IdropDataData[] = [
  {
    name: 'Blob Detection',
    icon: <FontAwesomeIcon icon={faDroplet} />,
    id: 'blob',
  },
]
