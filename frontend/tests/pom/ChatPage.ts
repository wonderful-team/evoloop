import { type Page, type Locator, expect } from "@playwright/test"

export class ChatPage {
  readonly page: Page
  readonly chatInput: Locator
  readonly sendButton: Locator
  readonly messageList: Locator
  readonly stopButton: Locator
  readonly newChatButton: Locator
  readonly sidebarToggle: Locator

  constructor(page: Page) {
    this.page = page
    this.chatInput = page.getByTestId("chat-input")
    this.sendButton = page.getByTestId("send-button")
    this.messageList = page.getByTestId("message-list")
    this.stopButton = page.getByRole("button", { name: /stop/i })
    this.newChatButton = page.getByTestId("new-chat-button")
    this.sidebarToggle = page.getByTestId("sidebar-toggle")
  }

  async goto() {
    await this.page.goto("/")
    await this.waitForReady()
  }

  async waitForReady() {
    await expect(this.chatInput).toBeVisible()
  }

  async sendMessage(message: string) {
    await this.chatInput.fill(message)
    await this.sendButton.click()
  }

  async getMessages() {
    return this.messageList.getByTestId("chat-message").all()
  }

  async getLastMessage() {
    const messages = await this.getMessages()
    return messages[messages.length - 1]
  }

  async waitForResponse(timeout = 30000) {
    await expect(this.stopButton).not.toBeVisible({ timeout })
  }

  async startNewChat() {
    await this.newChatButton.click()
  }

  async toggleSidebar() {
    await this.sidebarToggle.click()
  }

  async expectMessageVisible(text: string) {
    await expect(this.page.getByText(text)).toBeVisible()
  }

  async uploadFile(filePath: string) {
    const fileInput = this.page.locator('input[type="file"]')
    await fileInput.setInputFiles(filePath)
  }

  async attachImage(filePath: string) {
    await this.uploadFile(filePath)
  }
}
