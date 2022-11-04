import datetime
import uuid
class Blog():
    def __init__(self, author, title, content, tag, date, url=None):
        self.id = str(uuid.uuid4())
        self.author = author
        self.title = title
        self.content = content
        self.tag = tag
        self.date =  datetime.datetime.now()
        self.url = url
    def __repr__(self):
        return(
            f'Blog(\
                id={self.id},\
                author={self.author},\
                title={self.title},\
                content={self.content},\
                tag={self.tag},\
                date={self.date}\
                url={self.url}\
            )'
        )
    def to_dict(self):
        return {
            'id': self.id,
            'author': self.author,
            'title': self.title,
            'content': self.content,
            'tag': self.tag,
            'date': self.date,
            'url': self.url
        }