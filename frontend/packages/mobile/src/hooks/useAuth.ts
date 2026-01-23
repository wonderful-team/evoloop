/**
 * Mobile-specific Auth Hook
 * Uses the mobile client API instead of desktop SDK
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { AuthService, LoginService } from "../client"
import { handleError } from "../utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("evoloop_token") !== null
}

export interface UserRegister {
  username?: string
  password?: string
  email?: string
  nickname?: string
  mobile?: string
}

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  // For mobile, we get user info from the cloud API
  const { data: user } = useQuery<any | null, Error>({
    queryKey: ["currentUser"],
    queryFn: async () => {
      // Mobile uses evoloop_token stored during login
      const token = localStorage.getItem("evoloop_token")
      if (!token) return null
      // The mobile client handles token in axios interceptor
      return { token } // Simplified user object for mobile
    },
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      AuthService.registerUsername(data as any),
    onSuccess: () => {
      navigate({ to: "/login" as any })
    },
    onError: (err: any) => showErrorToast(err.message || "Registration failed"),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: { username: string; password: string }) => {
    const response = await LoginService.login(data)
    if (response.code === 0 && response.data?.token) {
      localStorage.setItem("evoloop_token", response.data.token)
      if (response.data.member_id) {
        localStorage.setItem("evoloop_member_id", String(response.data.member_id))
      }
    } else {
      throw new Error(response.message || "Login failed")
    }
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      // Navigate to tabs/devices after login
      navigate({ to: "/" as any })
    },
    onError: (err: any) => showErrorToast(err.message || "Login failed"),
  })

  const logout = async () => {
    try {
      await LoginService.logout()
    } catch (e) {
      console.error("Logout cleanup failed:", e)
    } finally {
      localStorage.removeItem("evoloop_token")
      localStorage.removeItem("evoloop_member_id")
      queryClient.resetQueries()
    }
  }

  return {
    signUpMutation,
    loginMutation,
    logout,
    user,
  }
}

export { isLoggedIn }
export default useAuth
