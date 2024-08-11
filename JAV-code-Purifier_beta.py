def play_video_segment(self):
        if self.current_segment >= len(self.start_frames):
            self.cap.release()
            self.preview_label.config(text="视频预览完成")
            return

        if self.frame_count == 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frames[self.current_segment])

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            image.thumbnail((400, 300))
            photo = ImageTk.PhotoImage(image=image)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(200, 150, image=photo)
            self.preview_canvas.image = photo

            elapsed_time = time.time() - self.start_time
            self.preview_label.config(text=f"预览中: {int(elapsed_time)}秒 / {int(self.preview_duration)}秒")

            self.frame_count += 1
            if self.frame_count >= self.frames_per_segment:
                self.frame_count = 0
                self.current_segment += 1

            if elapsed_time < self.preview_duration:
                self.master.after(int(1000/self.cap.get(cv2.CAP_PROP_FPS)), self.play_video_segment)
            else:
                self.cap.release()
                self.preview_label.config(text="视频预览完成")
        else:
            self.current_segment += 1
            self.frame_count = 0
            self.play_video_segment()
