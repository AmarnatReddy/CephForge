const BASE_URL = import.meta.env.VITE_API_URL || ''

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl
  }

  private async request<T = any>(method: string, path: string, data?: any): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
      body: data ? JSON.stringify(data) : undefined,
      redirect: 'follow',
    })

    if (!response.ok) {
      const errorBody = await response.text()
      throw new Error(errorBody || `API Error: ${response.status}`)
    }

    const text = await response.text()
    return text ? JSON.parse(text) : {}
  }

  async get<T = any>(path: string): Promise<T> {
    return this.request<T>('GET', path)
  }

  async post<T = any>(path: string, data?: any): Promise<T> {
    return this.request<T>('POST', path, data)
  }

  async put<T = any>(path: string, data: any): Promise<T> {
    return this.request<T>('PUT', path, data)
  }

  async delete<T = any>(path: string): Promise<T> {
    return this.request<T>('DELETE', path)
  }
}

export const api = new ApiClient(BASE_URL)
