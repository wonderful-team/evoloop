import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useEffect } from "react"
import { z } from "zod"

import type { Body_login_login_access_token as AccessToken } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { WechatLoginButton } from "@/components/Auth/WechatLogin"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@evoloop/shared/components/ui/form"
import { Input } from "@evoloop/shared/components/ui/input"
import { LoadingButton } from "@evoloop/shared/components/ui/loading-button"
import { PasswordInput } from "@evoloop/shared/components/ui/password-input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

// Schema needs to be inside or passed t function, but for simplicity we can move it inside component or use a function creator.
// Moving schema inside component is safer for i18n
const createSchema = (t: any) =>
  z.object({
    username: z.string().min(1, t("auth.errors.usernameRequired")),
    password: z
      .string()
      .min(1, { message: t("auth.errors.passwordRequired") })
      .min(8, { message: t("auth.errors.passwordMin8") }),
  }) satisfies z.ZodType<AccessToken>

type FormData = z.infer<ReturnType<typeof createSchema>>

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => {
    // Use i18n directly since head doesn't have access to hook
    // This runs before component, so we use a static approach
    // The title will be updated by the component's useEffect
    return {
      meta: [
        {
          title: "Log In - EvoLoop",
        },
      ],
    }
  },
})

function Login() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // Update page title dynamically
  useEffect(() => {
    document.title = t("auth.login.pageTitle", "Log In - EvoLoop")
  }, [t])

  const { loginMutation } = useAuth()
  const formSchema = createSchema(t)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      username: "",
      password: "",
    },
  })

  // 处理登录后的跳转逻辑
  const handlePostLoginRedirect = () => {
    const redirectPath = localStorage.getItem('redirect_after_login')
    if (redirectPath) {
      localStorage.removeItem('redirect_after_login')
      console.log('[Login] Redirecting to saved path:', redirectPath)
      // 解析hash路径，格式为 #/chat?thread_id=xxx
      const hashMatch = redirectPath.match(/^#(\/.+)$/)
      if (hashMatch) {
        const pathWithSearch = hashMatch[1]
        const [path, search] = pathWithSearch.split('?')
        navigate({ 
          to: path,
          search: search ? Object.fromEntries(new URLSearchParams(search)) : undefined
        })
        return
      }
    }
    // 默认跳转到首页
    navigate({ to: "/" })
  }

  const onSubmit = (data: FormData) => {
    if (loginMutation.isPending) return
    loginMutation.mutate(data, {
      onSuccess: () => {
        handlePostLoginRedirect()
      }
    })
  }

  const handleWechatLogin = (token: string) => {
    localStorage.setItem("access_token", token)
    localStorage.setItem("evoloop_token", token)
    handlePostLoginRedirect()
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-6">
          <div className="flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-bold">
              {t("auth.login.desktopTitle")}
            </h1>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("auth.login.emailOrUsername")}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="email-input"
                      placeholder={t("auth.login.emailOrUsername")}
                      type="text"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center">
                    <FormLabel>{t("auth.login.passwordPlaceholder")}</FormLabel>
                    <RouterLink
                      to="/recover-password"
                      className="ml-auto text-sm underline-offset-4 hover:underline"
                    >
                      {t("auth.login.forgotPassword")}
                    </RouterLink>
                  </div>
                  <FormControl>
                    <PasswordInput
                      data-testid="password-input"
                      placeholder={t("auth.login.passwordPlaceholder")}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <LoadingButton type="submit" loading={loginMutation.isPending}>
              {t("auth.login.submit")}
            </LoadingButton>

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground">
                  {t("auth.login.orContinueWith", "或使用其他方式")}
                </span>
              </div>
            </div>

            {/* WeChat Login */}
            <WechatLoginButton onSuccess={handleWechatLogin} />
          </div>

          <div className="text-center text-sm">
            {t("auth.login.noAccount")}{" "}
            <RouterLink to="/signup" className="underline underline-offset-4">
              {t("auth.login.signUp")}
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
