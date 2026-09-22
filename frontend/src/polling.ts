// Schedule after completion, so a slow request never overlaps the next poll.
export function poll(task: (signal: AbortSignal) => Promise<boolean | void>, interval: number) {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const tick = async () => {
    let keepGoing: boolean | void = true
    try { keepGoing = await task(controller.signal) }
    finally {
      if (!controller.signal.aborted && keepGoing !== false) timer = setTimeout(tick, interval)
    }
  }
  void tick()
  return () => { controller.abort(); if (timer) clearTimeout(timer) }
}
