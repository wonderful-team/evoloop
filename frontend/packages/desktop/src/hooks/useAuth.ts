import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  MemberService,
  AuthService,
  type UserPublic,
  UsersService,
} from "@/client"
import { handleError } from "@/utils"
import useCustomToast from "@evoloop/shared/hooks/useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

// Define local UserRegister type or import MemberRegisterUsernameData
export interface UserRegister {
  [key: string]: unknown // Required by generated MemberService type
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

  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: () => UsersService.readUserMe(), // Fix: Wrapping in arrow function
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      AuthService.registerUsername({ requestBody: data as any }), // Fix: Use AuthService
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken) => {
    const response = await LoginService.loginAccessToken({
      formData: data,
    })
    localStorage.setItem("access_token", response.access_token)
    // Set evoloop_token for consistency with EvoLoopApi/Mobile logic
    localStorage.setItem("evoloop_token", response.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = async () => {
    try {
      // Call backend to cleanup EvoLoop connection
      await MemberService.logout()
    } catch (e) {
      console.error("Logout cleanup failed:", e)
    } finally {
      // Clear PC token
      localStorage.removeItem("access_token")

      // Clear Mobile tokens (EvoLoop Link)
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

export { isLoggedIn, useAuth }
export default useAuth
