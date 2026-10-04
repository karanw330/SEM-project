const API_BASE_URL = window.location.origin.includes('http') 
  ? window.location.origin 
  : 'http://127.0.0.1:8000';

class ApiClient {
  static async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    try {
      const response = await fetch(url, { ...options, headers });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP Error ${response.status}`);
      }
      return await response.json();
    } catch (err) {
      console.error(`API Request Failed [${endpoint}]:`, err);
      throw err;
    }
  }

  // Dashboard Stats
  static async getDashboardStats(startTs = null, endTs = null) {
    const query = new URLSearchParams();
    if (startTs) query.append('start_ts', startTs);
    if (endTs) query.append('end_ts', endTs);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request(`/api/dashboard/stats${qs}`);
  }

  // Transactions
  static async getTransactions(filters = {}) {
    const query = new URLSearchParams();
    if (filters.startTs) query.append('start_ts', filters.startTs);
    if (filters.endTs) query.append('end_ts', filters.endTs);
    if (filters.search) query.append('search', filters.search);
    if (filters.type) query.append('tx_type', filters.type);
    if (filters.tagId) query.append('tag_id', filters.tagId);
    if (filters.untaggedOnly) query.append('untagged_only', 'true');

    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request(`/api/transactions${qs}`);
  }

  static async createTransaction(txData) {
    return this.request('/api/transactions', {
      method: 'POST',
      body: JSON.stringify(txData)
    });
  }

  static async updateTransaction(id, txData) {
    return this.request(`/api/transactions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(txData)
    });
  }

  static async updateTransactionTag(id, tagId) {
    return this.request(`/api/transactions/${id}/tag`, {
      method: 'PUT',
      body: JSON.stringify({ tag_id: tagId })
    });
  }

  static async deleteTransaction(id) {
    return this.request(`/api/transactions/${id}`, {
      method: 'DELETE'
    });
  }

  static async parsePDF(file, password = '') {
    const formData = new FormData();
    formData.append('file', file);
    if (password) formData.append('password', password);

    const response = await fetch(`${API_BASE_URL}/api/transactions/parse-pdf`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `PDF Upload failed: HTTP ${response.status}`);
    }
    return await response.json();
  }

  static async confirmImport(transactions) {
    return this.request('/api/transactions/confirm-import', {
      method: 'POST',
      body: JSON.stringify({ transactions })
    });
  }

  // Tags
  static async getTags() {
    return this.request('/api/tags');
  }

  static async createTag(tagData) {
    return this.request('/api/tags', {
      method: 'POST',
      body: JSON.stringify(tagData)
    });
  }

  static async updateTag(id, tagData) {
    return this.request(`/api/tags/${id}`, {
      method: 'PUT',
      body: JSON.stringify(tagData)
    });
  }

  static async deleteTag(id) {
    return this.request(`/api/tags/${id}`, {
      method: 'DELETE'
    });
  }

  // Auto-Tag Rules
  static async getRules() {
    return this.request('/api/rules');
  }

  static async createRule(ruleData) {
    return this.request('/api/rules', {
      method: 'POST',
      body: JSON.stringify(ruleData)
    });
  }

  static async deleteRule(id) {
    return this.request(`/api/rules/${id}`, {
      method: 'DELETE'
    });
  }

  static async applyAllRules() {
    return this.request('/api/rules/apply-all', {
      method: 'POST'
    });
  }

  // Seed Data
  static async seedDemoData() {
    return this.request('/api/seed', {
      method: 'POST'
    });
  }
}

window.ApiClient = ApiClient;
