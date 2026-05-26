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
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: () => MemberService.readUserMe(),
    enabled: isLoggedIn(),
  })

  const registerConfigQuery = useQuery({
    queryKey: ["registerConfig"],
    queryFn: () => AuthService.getRegisterConfig(),
  })

  const signUpMutation = useMutation({
    mutationFn: async (data: UserRegister) => {
      const res = await AuthService.registerUsername({ requestBody: data as any })
      if (res.code !== undefined && res.code < 0) {
        throw new Error(res.message || "Registration failed")
      }
      return res
    },
    onSuccess: () => {
      showSuccessToast("注册成功")
      navigate({ to: "/login" })
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Something went wrong.")
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const registerMobileMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await AuthService.registerMobile({ requestBody: data })
      if (res.code !== undefined && res.code < 0) {
        throw new Error(res.message || "Registration failed")
      }
      return res
    },
    onSuccess: () => {
      showSuccessToast("注册成功")
      navigate({ to: "/login" })
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Something went wrong.")
    },
  })

  const resetPasswordMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await AuthService.resetPassword({ requestBody: data })
      if (res.code !== undefined && res.code < 0) {
        throw new Error(res.message || "Reset failed")
      }
      return res
    },
    onSuccess: () => {
      showSuccessToast("密码重置成功")
      navigate({ to: "/login" })
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Something went wrong.")
    },
  })

  const login = async (data: any) => {
    const response = await AccountService.loginAccessToken({
      formData: data as any,
    })
    localStorage.setItem("access_token", response.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const requestMobileCodeMutation = useMutation({
    mutationFn: async (data: { mobile: string; captcha_id?: string; captcha_code?: string; type?: string }) => {
      // Provide a default type 'login' if not specified
      const requestData = { type: 'login', ...data }
      const res = await AuthService.sendSms({ requestBody: requestData as any })
      if (res.code !== undefined && res.code < 0) {
        throw new Error(res.message || "Failed to send code")
      }
      return res
    },
    onError: (err: any) => {
      showErrorToast(err.message || "Something went wrong.")
    },
  })

  const loginMobileMutation = useMutation({
    mutationFn: async (data: { mobile: string; code: string; key: string }) => {
      const response = await AccountService.loginMobile({ requestBody: data })
      localStorage.setItem("access_token", response.access_token)
      return response
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = async () => {
    try {
      await AccountService.logout()
    } catch (e) {
      console.error("Logout cleanup failed:", e)
    } finally {
      localStorage.removeItem("access_token")
      localStorage.removeItem("evoloop_member_id")
      // clear the query cache to avoid refetching without a token
      queryClient.clear()
      // manually navigate to login to unmount protected components
      navigate({ to: "/login" })
    }
  }

  return {
    registerConfigQuery,
    signUpMutation,
    registerMobileMutation,
    resetPasswordMutation,
    loginMutation,
    requestMobileCodeMutation,
    loginMobileMutation,
    logout,
    user,
  }
}

export { isLoggedIn, useAuth }
export default useAuth
