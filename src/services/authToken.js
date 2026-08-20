export const isJwtExpired = (token, now = Date.now()) => {
  if (!token) return true

  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return typeof payload.exp !== 'number' || payload.exp * 1000 <= now
  } catch {
    return true
  }
}
