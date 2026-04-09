import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  AccountService,
  MemberService,
  AuthService,
  type UserPublic,
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
    queryFn: () => MemberService.readUserMe(),
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

  const login = async (data: any) => {
    const response = await AccountService.loginAccessToken({
      formData: data as any, // Cast to any because the generated data.formData expects AccountLoginAccessTokenData
    })
    localStorage.setItem("access_token", response.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      // Invalidate current user query to force refetch
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const requestMobileCodeMutation = useMutation({
    mutationFn: (data: { mobile: string; captcha_id?: string; captcha_code?: string }) =>
      AccountService.requestMobileCode({ requestBody: data }),
    onError: handleError.bind(showErrorToast),
  })

  const loginMobileMutation = useMutation({
    mutationFn: async (data: { mobile: string; code: string; key: string }) => {
      const response = await AccountService.loginMobile({ requestBody: data })
      localStorage.setItem("access_token", response.access_token)
      return response
    },
    onSuccess: () => {
      // Invalidate current user query to force refetch
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = async () => {
    try {
      // Call backend to cleanup EvoLoop connection
      await AccountService.logout()
    } catch (e) {
      console.error("Logout cleanup failed:", e)
    } finally {
      // Clear access token
      localStorage.removeItem("access_token")
      localStorage.removeItem("evoloop_member_id")

      queryClient.resetQueries()
    }
  }

  return {
    signUpMutation,
    loginMutation,
    requestMobileCodeMutation,
    loginMobileMutation,
    logout,
    user,
  }
}

export { isLoggedIn, useAuth }
export default useAuth
