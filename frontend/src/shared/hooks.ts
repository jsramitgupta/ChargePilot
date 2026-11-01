import { useQuery } from '@tanstack/react-query'

import { fetchSession } from './api'

export function useSession() {
  return useQuery({
    queryKey: ['session'],
    queryFn: fetchSession,
    retry: false,
  })
}
