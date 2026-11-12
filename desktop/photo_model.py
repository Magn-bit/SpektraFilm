"""Virtualized lightweight filmstrip; edit graphs stay in the controller."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSortFilterProxyModel, Property, Signal, Slot


class PhotoListModel(QAbstractListModel):
    PHOTO_ROLE=int(Qt.UserRole)+1

    def __init__(self,rows,parent=None):
        super().__init__(parent)
        self.rows=rows

    def roleNames(self):return {self.PHOTO_ROLE:b'photo'}

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows):return None
        item=self.rows[index.row()]
        if role==self.PHOTO_ROLE:
            return {key:item.get(key) for key in ('path','name','dimensions','thumbnail','width','height')}
        if role==Qt.DisplayRole:return item['name']
        return None

    def append(self,items):
        if not items:return
        first=len(self.rows)
        self.beginInsertRows(QModelIndex(),first,first+len(items)-1)
        self.rows.extend(items)
        self.endInsertRows()

    def replace(self,rows):
        self.beginResetModel();self.rows=rows;self.endResetModel()

    def changed(self,row):
        if 0<=row<len(self.rows):
            index=self.index(row,0);self.dataChanged.emit(index,index,[self.PHOTO_ROLE])


class PhotoBrowserModel(QSortFilterProxyModel):
    """A view of the same session, without copying edit graphs or decoding RAWs."""
    changed=Signal()
    INDEX_ROLE=PhotoListModel.PHOTO_ROLE+1

    def __init__(self,source,parent=None):
        super().__init__(parent)
        self._query='';self._order='import'
        self.setSourceModel(source);self.setDynamicSortFilter(True)

    def roleNames(self):return dict(super().roleNames())|{self.INDEX_ROLE:b'sourceIndex'}

    def data(self,index,role=Qt.DisplayRole):
        if role==self.INDEX_ROLE:return self.mapToSource(index).row()
        return super().data(index,role)

    @Property(str,notify=changed)
    def query(self):return self._query
    @query.setter
    def query(self,value):
        value=str(value).strip().casefold()
        if value!=self._query:self._query=value;self.invalidateFilter();self.changed.emit()

    @Property(str,notify=changed)
    def order(self):return self._order
    @order.setter
    def order(self,value):
        if value not in ('import','name','name_desc'):return
        self._order=value
        self.sort(-1 if value=='import' else 0,Qt.DescendingOrder if value=='name_desc' else Qt.AscendingOrder)
        self.changed.emit()

    def filterAcceptsRow(self,row,parent):
        if not self._query:return True
        item=self.sourceModel().rows[row]
        return self._query in (str(item.get('name',''))+' '+str(item.get('path',''))).casefold()

    def lessThan(self,left,right):
        rows=self.sourceModel().rows
        a,b=rows[left.row()],rows[right.row()]
        return (a['name'].casefold(),a['path'])<(b['name'].casefold(),b['path'])
