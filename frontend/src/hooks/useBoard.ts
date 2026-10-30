import { useCallback, useEffect, useRef, useState } from 'react'

import { getBoardApi } from '@/api/room'
import type { BoardData } from '@/types'

/** 看板数据：20 秒轮询，页面隐藏时暂停，支持手动刷新 */
export function useBoard(date: string) {
  const [data, setData] = useState<BoardData | null>(null)
  const [loading, setLoading] = useState(true)
  const requestIdRef = useRef(0)

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current
    try {
      const res = await getBoardApi(date)
      if (requestId === requestIdRef.current) {
        setData(res.data)
      }
    } catch {
      // 错误提示由请求拦截器统一处理
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [date])

  useEffect(() => {
    setLoading(true)
    void load()
    const timer = window.setInterval(() => {
      if (!document.hidden) {
        void load()
      }
    }, 20000)
    return () => {
      window.clearInterval(timer)
    }
  }, [load])

  return { data, loading, refresh: load }
}
