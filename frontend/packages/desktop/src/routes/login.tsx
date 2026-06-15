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
import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { WechatLoginButton } from "@/components/Auth/WechatLogin"
import { AuthLayout } from "@/components/Common/AuthLayout"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

const searchSchema = z.object({
  session_expired: z.string().optional().catch(undefined),
})

// Schema needs to be inside or passed t function, but for simplicity we can move it inside component or use a function creator.
// Moving schema inside component is safer for i18n
const createSchema = (t: any) =>
  z.object({
    username: z.string().min(1, t("auth.errors.usernameRequired")),
    password: z
      .string()
      .min(1, { message: t("auth.errors.passwordRequired") })
      .min(8, { message: t("auth.errors.passwordMin8") }),
  })

type FormData = z.infer<ReturnType<typeof createSchema>>

export const Route = createFileRoute("/login")({
  component: Login,
  validateSearch: searchSchema,
  beforeLoad: async ({ search }) => {
    // Allow access to /login when session_expired is set (from 401 handler)
    // to avoid redirect loops when the backend session is invalid but cookie remains.
    if (isLoggedIn() && !search.session_expired) {
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

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@evoloop/shared/components/ui/tabs"
import { MobileLogin } from "@/components/Auth/MobileLogin"

function Login() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // Update page title dynamically
  useEffect(() => {
    document.title = t("auth.login.pageTitle")
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
    const redirectPath = localStorage.getItem("redirect_after_login")
    if (redirectPath) {
      localStorage.removeItem("redirect_after_login")
      console.log("[Login] Redirecting to saved path:", redirectPath)
      const hashMatch = redirectPath.match(/^#(\/.+)$/)
      if (hashMatch) {
        const pathWithSearch = hashMatch[1]
        const [path, search] = pathWithSearch.split("?")
        navigate({
          to: path,
          search: search
            ? Object.fromEntries(new URLSearchParams(search))
            : undefined,
        })
        return
      }
    }
    // Strip session_expired param on successful login
    navigate({ to: "/", search: {} })
  }

  const onSubmit = (data: FormData) => {
    if (loginMutation.isPending) return
    loginMutation.mutate(data, {
      onSuccess: () => {
        handlePostLoginRedirect()
      },
    })
  }

  const handleThirdPartyLoginSuccess = () => {
    // Backend sets session cookie for all login flows.
    // Frontend no longer stores tokens in localStorage.
    handlePostLoginRedirect()
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-2xl font-bold">{t("auth.login.desktopTitle")}</h1>
        </div>

        <Tabs defaultValue="account" className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-4">
            <TabsTrigger value="account">
              {t("auth.login.accountTab")}
            </TabsTrigger>
            <TabsTrigger value="mobile">
              {t("auth.login.mobileTab")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="account">
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="space-y-4"
              >
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
                        <FormLabel>
                          {t("auth.login.passwordPlaceholder")}
                        </FormLabel>
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

                <LoadingButton
                  type="submit"
                  className="w-full"
                  loading={loginMutation.isPending}
                >
                  {t("auth.login.submit")}
                </LoadingButton>
              </form>
            </Form>
          </TabsContent>

          <TabsContent value="mobile">
            <MobileLogin onSuccess={handleThirdPartyLoginSuccess} />
          </TabsContent>
        </Tabs>

        {/* Divider */}
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-background px-2 text-muted-foreground">
              {t("auth.login.orContinueWith")}
            </span>
          </div>
        </div>

        {/* WeChat Login */}
        <WechatLoginButton onSuccess={handleThirdPartyLoginSuccess} />

        <div className="text-center text-sm">
          {t("auth.login.noAccount")}{" "}
          <RouterLink to="/signup" className="underline underline-offset-4">
            {t("auth.login.signUp")}
          </RouterLink>
        </div>
      </div>
    </AuthLayout>
  )
}
