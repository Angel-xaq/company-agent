/** 将 HH:mm 转为当天分钟数 */
export function toMinutes(value: string): number {
  const [hour, minute] = value.split(':').map(Number)
  return hour * 60 + minute
}

/** 将分钟数格式化为 HH:mm */
export function fromMinutes(total: number): string {
  const hour = Math.floor(total / 60)
  const minute = total % 60
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

/** 生成可选的开始时段（不包含营业结束时刻） */
export function buildStartSlots(
  start: string,
  end: string,
  stepMinutes: number
): string[] {
  const startTotal = toMinutes(start)
  const endTotal = toMinutes(end)
  const slots: string[] = []
  for (let current = startTotal; current + stepMinutes <= endTotal; current += stepMinutes) {
    slots.push(fromMinutes(current))
  }
  return slots
}

/** 生成可选的结束时段（包含营业结束时刻） */
export function buildEndSlots(
  start: string,
  end: string,
  stepMinutes: number
): string[] {
  const startTotal = toMinutes(start)
  const endTotal = toMinutes(end)
  const slots: string[] = []
  for (let current = startTotal + stepMinutes; current <= endTotal; current += stepMinutes) {
    slots.push(fromMinutes(current))
  }
  return slots
}
