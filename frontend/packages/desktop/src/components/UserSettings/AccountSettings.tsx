import ChangePassword from "./ChangePassword"
import UserInformation from "./UserInformation"

export function AccountSettings() {
  return (
    <div className="flex flex-col gap-8">
      <UserInformation />
      <ChangePassword />
    </div>
  )
}
