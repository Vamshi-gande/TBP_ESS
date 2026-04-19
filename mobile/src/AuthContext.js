/**
 * Auth context — provides login/logout + token state to all screens.
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { loadToken, clearToken, login as apiLogin } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadToken().then((t) => {
      setTokenState(t);
      setLoading(false);
    });
  }, []);

  const login = async (username, password) => {
    const data = await apiLogin(username, password);
    setTokenState(data.access_token);
    return data;
  };

  const logout = async () => {
    await clearToken();
    setTokenState(null);
  };

  return (
    <AuthContext.Provider value={{ token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
